# Observability Libs

[![Release to Edge](https://github.com/canonical/observability-libs/actions/workflows/release-edge.yaml/badge.svg)](https://github.com/canonical/observability-libs/actions/workflows/release-edge.yaml)
[![Release Libraries](https://github.com/canonical/observability-libs/actions/workflows/release-libs.yaml/badge.svg)](https://github.com/canonical/observability-libs/actions/workflows/release-libs.yaml)
[![Discourse Status](https://img.shields.io/discourse/status?server=https%3A%2F%2Fdiscourse.charmhub.io&style=flat&label=CharmHub%20Discourse)](https://discourse.charmhub.io)

## Description

Observability Libs is a placeholder charm that is used to provide a home for [charm libraries] that
are used for the development of charms deployed as part of the LMA Light [bundle].

## Usage

While it is possible to deploy this charm, it is only a tester charm and is
intended to be deployed only for testing purposes.

```shell
charmcraft pack
juju deploy ./observability-libs_ubuntu-20.04-amd64.charm \
  --resource placeholder-image=busybox
```

Where this charm should be used, is to access one of the following libraries during development:

- [KubernetesServicePatch] - a small library used to patch the Juju auto-created Kubernetes Service
  during the deployment of a sidecar charm to contain the correct ports for an application.

- [KubernetesComputeResourcesPatch] - a small library used to patch the Juju
  auto-created statefulset with custom resource limits.

- [JujuTopology] - Used to create and output Juju topologies either from charms, relation data, or parts.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and `CONTRIBUTING.md` for developer guidance.

[KubernetesServicePatch]: https://charmhub.io/observability-libs/libraries/kubernetes_service_patch
[KubernetesComputeResourcesPatch]: https://charmhub.io/observability-libs/libraries/kubernetes_compute_resources_patch
[bundle]: https://charmhub.io/lma-light
[charm libraries]: https://juju.is/docs/sdk/libraries
[JujuTopology]: https://charmhub.io/observability-libs/libraries/juju_topology
