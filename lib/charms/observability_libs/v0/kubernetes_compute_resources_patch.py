# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""# KubernetesComputeResourcesPatch Library.

This library is designed to enable developers to more simply patch the Kubernetes compute resource
limits and requests created by Juju during the deployment of a sidecar charm.

When initialised, this library binds a handler to the parent charm's `config-changed` event.
The config-changed event is used because it is guaranteed to fire on startup, on upgrade and on
pod churn. Additionally, resource limits may be set by charm config options, which would also be
caught out-of-the-box by this handler. The handler applies the patch to the app's StatefulSet.
This should ensure that the resource limits are correct throughout the charm's life.Additional
optional user-provided events for re-applying the patch are supported but discouraged.

The constructor takes a reference to the parent charm, a 'limits' and a 'requests' dictionaries
that together define the resource requirements. For information regarding the `lightkube`
`ResourceRequirements` model, please visit the `lightkube`
[docs](https://gtsystem.github.io/lightkube-models/1.23/models/core_v1/#resourcerequirements).


## Getting Started

To get started using the library, you just need to fetch the library using `charmcraft`. **Note
that you also need to add `lightkube` and `lightkube-models` to your charm's `requirements.txt`.**

```shell
cd some-charm
charmcraft fetch-lib charms.observability_libs.v0.kubernetes_compute_resources_patch
cat << EOF >> requirements.txt
lightkube
lightkube-models
EOF
```

Then, to initialise the library:

```python
# ...
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    KubernetesComputeResourcesPatch
)

class SomeCharm(CharmBase):
  def __init__(self, *args):
    # ...
    self.resources_patch = KubernetesComputeResourcesPatch(
        self,
        "container-name",
        limits_func=lambda: {"cpu": "1", "mem": "2Gi"},
        requests_func=lambda: {"cpu": "1", "mem": "2Gi"}
    )
    # ...
```

Or, if, for example, the resource specs are coming from config options:

```python
# ...

class SomeCharm(CharmBase):
  def __init__(self, *args):
    # ...
    self.resources_patch = KubernetesComputeResourcesPatch(
        self,
        "container-name",
        limits_func=lambda: self._resource_spec_from_config(),
        requests_func=lambda: self._resource_spec_from_config(),
    )

  def _resource_spec_from_config(self):
    return {"cpu": self.model.config.get("cpu"), "memory": self.model.config.get("memory")}

    # ...
```


Additionally, you may wish to use mocks in your charm's unit testing to ensure that the library
does not try to make any API calls, or open any files during testing that are unlikely to be
present, and could break your tests. The easiest way to do this is during your test `setUp`:

```python
# ...

@patch.multiple(
    "charm.KubernetesComputeResourcesPatch",
    _namespace="test-namespace",
    _is_patched=lambda *a, **kw: True,
    is_ready=lambda *a, **kw: True,
)
@patch("lightkube.core.client.GenericSyncClient")
def setUp(self, *unused):
    self.harness = Harness(SomeCharm)
    # ...
```
"""
import decimal
import logging
from decimal import Decimal
from math import ceil, floor
from typing import Callable, Dict, List, Optional, TypedDict, Union

from lightkube import ApiError, Client
from lightkube.core import exceptions
from lightkube.models.apps_v1 import StatefulSetSpec
from lightkube.models.core_v1 import (
    Container,
    PodSpec,
    PodTemplateSpec,
    ResourceRequirements,
)
from lightkube.resources.apps_v1 import StatefulSet
from lightkube.resources.core_v1 import Pod
from lightkube.types import PatchType
from lightkube.utils.quantity import equals_canonically, parse_quantity
from ops.charm import CharmBase
from ops.framework import BoundEvent, EventBase, EventSource, Object, ObjectEvents

logger = logging.getLogger(__name__)

# The unique Charmhub library identifier, never change it
LIBID = "2a6066f701444e8db44ba2f6af28da90"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1


class ResourceSpecDict(TypedDict, total=False):
    """A dict representing a K8s resource limit.

    See:
    - https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
    - https://gtsystem.github.io/lightkube-models/1.23/models/core_v1/#resourcerequirements
    """

    cpu: Optional[str]
    memory: Optional[str]


_Decimal = Union[Decimal, float, str, int]  # types that are potentially convertible to Decimal


def ray_hopper(x: _Decimal, a1: _Decimal, a2: _Decimal, x0: _Decimal) -> Decimal:
    """A monotone ray hopper.

    For example, this could model the thrust of a hypothetical multi-stage rocket engine, as a
    function of time.

    Args:
        x: the value for which to calculate the function.
        a1: the slope of the first ray.
        a2: the slope of the second ray; must be a1 > a2.
        x0: the crossover point from the first ray (a1) to the second ray (a2); must be x0 > 0.

    Returns:
        A linear piecewise-continuous function of x given two "rays", y = a1*x and y = a2*x,
        and a crossover point x0, as follows:
        - x, if 0 <= x <= x0;
        - a1*x, if x0 < x <= a1/a2*x0;
        - a2*x, if a1/a2*x0 < x.

    >>> ray_hopper(1000, 1, "0.8", 200)  # take 0.8 * 1000
    Decimal('800.0')
    >>> ray_hopper(260, 1, "0.8", 200)  # take 0.8 * 260 (input value still > default / 0.8)
    Decimal('208.0')
    >>> ray_hopper(250, 1, "0.8", 200)  # take the default, 200 (input value <= default / 0.8)
    Decimal('200')
    >>> ray_hopper(200, 1, "0.8", 200)
    Decimal('200')
    >>> ray_hopper(150, 1, "0.8", 200)  # return the input value (input value < default)
    Decimal('150')
    """
    try:
        a1 = Decimal(a1)
        a2 = Decimal(a2)
        x = Decimal(x)
        x0 = Decimal(x0)
    except ArithmeticError:
        raise ValueError("Invalid argument(s): all args must be (convertible to) decimal.")

    if any(arg < 0 for arg in [x, a1, a2, x0]):
        raise ValueError("Invalid argument(s): all args must be greater than 0.")
    if a1 <= a2:
        raise ValueError("Invalid argument: must satisfy a1 > a2.")

    if x <= x0:
        return a1 * x

    a1x0 = a1 * x0
    if x <= a1x0 / a2:
        return a1x0

    return a2 * x


def limits_to_requests_scaled(
    resource_limits: ResourceSpecDict, default_requests: ResourceSpecDict, scaling_factor: _Decimal
) -> ResourceSpecDict:
    """A helper function for calculating "requests" from a "limits" dict using a scaling factor.

    With this function:
    - When the "limits" portion is high enough, the "requests" portion is scaled down
      proportionally, leaving some room for bursts.
    - When the "limits" portion is too low, no scaling takes place and the requests equals the
      limits.

    Args:
        resource_limits: A dictionary representation of K8s resource limits
        default_requests: The default requests values to use if a limits value is not given. This
            would also be used as the crossover point from requests = limits to the scaled limits.
            For example, we can set the "requests" portion of the resource limits to a sensible
            value, while keeping the "limits" portion unspecified.
        scaling_factor: A scaling factor used to calculate the requests value from the limits
            value. The scaling factor must satisfy: 0 < scaling_factor < 1.

    Raises:
        ValueError, if arguments are invalid or out of range.

    Returns:
        A resource spec dictionary scaled-down by scaling_factor, subject to the "default value"
         constraint as described above.

    >>> sf = Decimal("0.8")
    >>> limits_to_requests_scaled({"cpu": "1"}, {"cpu": "200m"}, sf)
    {'cpu': '0.800'}
    >>> limits_to_requests_scaled({"cpu": "260m"}, {"cpu": "200m"}, sf)
    {'cpu': '0.208'}
    >>> limits_to_requests_scaled({"cpu": "250m"}, {"cpu": "200m"}, sf)
    {'cpu': '0.200'}
    >>> limits_to_requests_scaled({"cpu": "200m"}, {"cpu": "200m"}, sf)
    {'cpu': '0.200'}
    >>> limits_to_requests_scaled({"cpu": "150m"}, {"cpu": "200m"}, sf)
    {'cpu': '0.150'}
    """
    scaling_factor = Decimal(scaling_factor)
    if not (0 < scaling_factor < 1):
        raise ValueError("scaling_factor must be in the range (0, 1).")

    if not is_valid_spec(resource_limits):
        raise ValueError("Invalid limits spec: {}".format(resource_limits))
    if not is_valid_spec(default_requests):
        raise ValueError("Invalid default requests spec: {}".format(default_requests))

    resource_limits = sanitize_resource_spec_dict(resource_limits) or {}
    default_requests = sanitize_resource_spec_dict(default_requests) or {}

    # Construct a "requests" dict from a "limits" dict (user input).
    # Default "requests" values will be used for any missing key in "limits".
    requests = {}
    for k in ResourceSpecDict.__annotations__.keys():
        if k in default_requests:
            default = parse_quantity(default_requests[k])  # type: ignore[literal-required]
            value = (
                ray_hopper(
                    parse_quantity(resource_limits[k]), Decimal("1.0"), scaling_factor, default  # type: ignore[literal-required, arg-type]
                )
                if k in resource_limits
                else default
            )
            requests[k] = str(value.quantize(decimal.Decimal("0.001"), rounding=decimal.ROUND_UP))  # type: ignore[union-attr]

    return ResourceSpecDict(requests)  # type: ignore[misc]


def is_valid_spec(spec: Optional[ResourceSpecDict], debug=False) -> bool:  # noqa: C901
    """Check if the spec dict is valid."""
    if spec is None:
        return True
    if not isinstance(spec, dict):
        if debug:
            logger.error("Invalid resource spec type '%s': must be either None or dict.", spec)
        return False

    for k, v in spec.items():
        if k not in ResourceSpecDict.__annotations__.keys():
            if debug:
                logger.error("Invalid resource spec entry: {%s: %s}.", k, v)
            return False
        try:
            assert isinstance(v, (str, type(None)))  # for type checker
            pv = parse_quantity(v)
        except ValueError:
            if debug:
                logger.error("Invalid resource spec entry: {%s: %s}.", k, v)
            return False

        if pv and pv < 0:
            if debug:
                logger.error("Invalid resource spec entry: {%s: %s}; must be non-negative.", k, v)
            return False

    return True


def sanitize_resource_spec_dict(spec: Optional[ResourceSpecDict]) -> Optional[ResourceSpecDict]:
    """Fix spec values without altering semantics.

    The purpose of this helper function is to correct known issues.
    This function is not intended for fixing user mistakes such as incorrect keys present; that is
    left for the `is_valid_spec` function.
    """
    if not spec:
        return spec

    d = spec.copy()

    for k, v in spec.items():
        if not v:
            # Need to ignore empty values input, otherwise the StatefulSet will have "0" as the
            # setpoint, the pod will not be scheduled and the charm would be stuck in unknown/lost.
            # This slightly changes the spec semantics compared to lightkube/k8s: a setpoint of
            # `None` would be interpreted here as "no limit".
            del d[k]  # type: ignore

    # Round up memory to whole bytes. This is need to avoid K8s errors such as:
    # fractional byte value "858993459200m" (0.8Gi) is invalid, must be an integer
    memory = d.get("memory")
    if memory:
        as_decimal = parse_quantity(memory)
        if as_decimal and as_decimal.remainder_near(floor(as_decimal)):
            d["memory"] = str(ceil(as_decimal))
    return d


class K8sResourcePatchFailedEvent(EventBase):
    """Emitted when patching fails."""

    def __init__(self, handle, message=None):
        super().__init__(handle)
        self.message = message

    def snapshot(self) -> Dict:
        """Save grafana source information."""
        return {"message": self.message}

    def restore(self, snapshot):
        """Restore grafana source information."""
        self.message = snapshot["message"]


class K8sResourcePatchEvents(ObjectEvents):
    """Events raised by :class:`K8sResourcePatchEvents`."""

    patch_failed = EventSource(K8sResourcePatchFailedEvent)


class ContainerNotFoundError(ValueError):
    """Raised when a given container does not exist in the list of containers."""


class ResourcePatcher:
    """Helper class for patching a container's resource limits in a given StatefulSet."""

    def __init__(self, namespace: str, statefulset_name: str, container_name: str):
        self.namespace = namespace
        self.statefulset_name = statefulset_name
        self.container_name = container_name
        self.client = Client()

    def _patched_delta(self, resource_reqs: ResourceRequirements) -> StatefulSet:
        statefulset = self.client.get(
            StatefulSet, name=self.statefulset_name, namespace=self.namespace
        )

        return StatefulSet(
            spec=StatefulSetSpec(
                selector=statefulset.spec.selector,  # type: ignore[attr-defined]
                serviceName=statefulset.spec.serviceName,  # type: ignore[attr-defined]
                template=PodTemplateSpec(
                    spec=PodSpec(
                        containers=[Container(name=self.container_name, resources=resource_reqs)]
                    )
                ),
            )
        )

    @classmethod
    def _get_container(cls, container_name: str, containers: List[Container]) -> Container:
        """Find our container from the container list, assuming list is unique by name.

        Typically, *.spec.containers[0] is the charm container, and [1] is the (only) workload.

        Raises:
            ContainerNotFoundError, if the user-provided container name does not exist in the list.

        Returns:
            An instance of :class:`Container` whose name matches the given name.
        """
        try:
            return next(iter(filter(lambda ctr: ctr.name == container_name, containers)))
        except StopIteration:
            raise ContainerNotFoundError(f"Container '{container_name}' not found")

    def is_patched(self, resource_reqs: ResourceRequirements) -> bool:
        """Reports if the resource patch has been applied to the StatefulSet.

        Returns:
            bool: A boolean indicating if the service patch has been applied.
        """
        return equals_canonically(self.get_templated(), resource_reqs)

    def get_templated(self) -> ResourceRequirements:
        """Returns the resource limits specified in the StatefulSet template."""
        statefulset = self.client.get(
            StatefulSet, name=self.statefulset_name, namespace=self.namespace
        )
        podspec_tpl = self._get_container(
            self.container_name,
            statefulset.spec.template.spec.containers,  # type: ignore[attr-defined]
        )
        return podspec_tpl.resources

    def get_actual(self, pod_name: str) -> ResourceRequirements:
        """Return the resource limits that are in effect for the container in the given pod."""
        pod = self.client.get(Pod, name=pod_name, namespace=self.namespace)
        podspec = self._get_container(
            self.container_name, pod.spec.containers  # type: ignore[attr-defined]
        )
        return podspec.resources

    def is_ready(self, pod_name, resource_reqs: ResourceRequirements):
        """Reports if the resource patch has been applied and is in effect.

        Returns:
            bool: A boolean indicating if the service patch has been applied and is in effect.
        """
        return self.is_patched(resource_reqs) and equals_canonically(
            resource_reqs, self.get_actual(pod_name)
        )

    def apply(self, resource_reqs: ResourceRequirements) -> None:
        """Patch the Kubernetes resources created by Juju to limit cpu or mem."""
        # Need to ignore invalid input, otherwise the StatefulSet gives "FailedCreate" and the
        # charm would be stuck in unknown/lost.
        if self.is_patched(resource_reqs):
            return

        self.client.patch(
            StatefulSet,
            self.statefulset_name,
            self._patched_delta(resource_reqs),
            namespace=self.namespace,
            patch_type=PatchType.APPLY,
            field_manager=self.__class__.__name__,
        )


class KubernetesComputeResourcesPatch(Object):
    """A utility for patching the Kubernetes compute resources set up by Juju."""

    on = K8sResourcePatchEvents()

    def __init__(
        self,
        charm: CharmBase,
        container_name: str,
        *,
        limits_func: Callable[[], Optional[ResourceSpecDict]],
        requests_func: Callable[[], Optional[ResourceSpecDict]],
        refresh_event: Optional[Union[BoundEvent, List[BoundEvent]]] = None,
    ):
        """Constructor for KubernetesComputeResourcesPatch.

        References:
            - https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/

        Args:
            charm: the charm that is instantiating the library.
            container_name: the container for which to apply the resource limits.
            limits_func: a callable returning a dictionary for `limits` resources; if raises,
              should only raise ValueError.
            requests_func: a callable returning a dictionary for `requests` resources; if raises,
              should only raise ValueError.
            refresh_event: an optional bound event or list of bound events which
                will be observed to re-apply the patch.
        """
        super().__init__(charm, "{}_{}".format(self.__class__.__name__, container_name))
        self._charm = charm
        self._container_name = container_name
        self.limits_func = limits_func
        self.requests_func = requests_func
        self.patcher = ResourcePatcher(self._namespace, self._app, container_name)

        # Ensure this patch is applied during the 'config-changed' event, which is emitted every
        # startup and every upgrade. The config-changed event is a good time to apply this kind of
        # patch because it is always emitted after storage-attached, leadership and peer-created,
        # all of which only fire after install. Patching the statefulset prematurely could result
        # in those events firing without a workload.
        self.framework.observe(charm.on.config_changed, self._on_config_changed)

        if not refresh_event:
            refresh_event = []
        elif not isinstance(refresh_event, list):
            refresh_event = [refresh_event]
        for ev in refresh_event:
            self.framework.observe(ev, self._on_config_changed)

    def _on_config_changed(self, _):
        self._patch()

    def _patch(self) -> None:
        """Patch the Kubernetes resources created by Juju to limit cpu or mem."""
        try:
            limits = self.limits_func()
            requests = self.requests_func()
        except ValueError as e:
            msg = f"Failed obtaining resource limit spec: {e}"
            logger.error(msg)
            self.on.patch_failed.emit(message=msg)
            return

        for spec in (limits, requests):
            if not is_valid_spec(spec):
                msg = f"Invalid resource limit spec: {spec}"
                logger.error(msg)
                self.on.patch_failed.emit(message=msg)
                return

        resource_reqs = ResourceRequirements(
            limits=sanitize_resource_spec_dict(limits),  # type: ignore[arg-type]
            requests=sanitize_resource_spec_dict(requests),  # type: ignore[arg-type]
        )

        try:
            self.patcher.apply(resource_reqs)

        except exceptions.ConfigError as e:
            msg = f"Error creating k8s client: {e}"
            logger.error(msg)
            self.on.patch_failed.emit(message=msg)
            return

        except ApiError as e:
            if e.status.code == 403:
                msg = f"Kubernetes resources patch failed: `juju trust` this application. {e}"
            else:
                msg = f"Kubernetes resources patch failed: {e}"

            logger.error(msg)
            self.on.patch_failed.emit(message=msg)

        except ValueError as e:
            msg = f"Kubernetes resources patch failed: {e}"
            logger.error(msg)
            self.on.patch_failed.emit(message=msg)

        else:
            logger.info(
                "Kubernetes resources for app '%s', container '%s' patched successfully: %s",
                self._app,
                self._container_name,
                resource_reqs,
            )

    def is_ready(self) -> bool:
        """Reports if the resource patch has been applied and is in effect.

        Returns:
            bool: A boolean indicating if the service patch has been applied and is in effect.
        """
        try:
            limits = self.limits_func()
            requests = self.requests_func()
        except ValueError as e:
            msg = f"Failed obtaining resource limit spec: {e}"
            logger.error(msg)
            return False

        if not is_valid_spec(limits) or not is_valid_spec(requests):
            return False

        resource_reqs = ResourceRequirements(
            limits=sanitize_resource_spec_dict(limits),  # type: ignore[arg-type]
            requests=sanitize_resource_spec_dict(requests),  # type: ignore[arg-type]
        )

        try:
            return self.patcher.is_ready(self._pod, resource_reqs)
        except (ValueError, ApiError) as e:
            msg = f"Failed to apply resource limit patch: {e}"
            logger.error(msg)
            self.on.patch_failed.emit(message=msg)
            return False

    @property
    def _app(self) -> str:
        """Name of the current Juju application.

        Returns:
            str: A string containing the name of the current Juju application.
        """
        return self._charm.app.name

    @property
    def _pod(self) -> str:
        """Name of the unit's pod.

        Returns:
            str: A string containing the name of the current unit's pod.
        """
        return "-".join(self._charm.unit.name.rsplit("/", 1))

    @property
    def _namespace(self) -> str:
        """The Kubernetes namespace we're running in.

        If a charm is deployed into the controller model (which certainly could happen as we move
        to representing the controller as a charm) then self._charm.model.name !== k8s namespace.
        Instead, the model name is controller in Juju and controller-<controller-name> for the
        namespace in K8s.

        Returns:
            str: A string containing the name of the current Kubernetes namespace.
        """
        with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r") as f:
            return f.read().strip()
