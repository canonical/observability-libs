# Observability Libs

## Description

Observability Libs is a placeholder charm that is used to provide a home for [charm libraries] that
are used for the development of charms deployed as part of the LMA Light [bundle].

## Usage

While it is possible to deploy this charm, it is essentially a no-op, and not what this charm was
designed for. Instructions are omitted. This may change in the near future.

Where this charm should be used, is to access one of the following libraries during development:

- [KubernetesServicePatch] - a small library used to patch the Juju auto-created Kubernetes Service
  during the deployment of a sidecar charm to contain the correct ports for an application.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and `CONTRIBUTING.md` for developer guidance.

[kubernetesservicepatch]: https://charmhub.io/observability-libs/libraries/kubernetes_service_patch
[bundle]: https://charmhub.io/lma-light
[charm libraries]: https://juju.is/docs/sdk/libraries
