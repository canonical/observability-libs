# Contributing to observability-libs

![GitHub License](https://img.shields.io/github/license/canonical/observability-libs)
![GitHub Commit Activity](https://img.shields.io/github/commit-activity/y/canonical/observability-libs)
![GitHub Lines of Code](https://img.shields.io/tokei/lines/github/canonical/observability-libs)
![GitHub Issues](https://img.shields.io/github/issues/canonical/observability-libs)
![GitHub PRs](https://img.shields.io/github/issues-pr/canonical/observability-libs)
![GitHub Contributors](https://img.shields.io/github/contributors/canonical/observability-libs)
![GitHub Watchers](https://img.shields.io/github/watchers/canonical/observability-libs?style=social)

## Bugs and pull requests

- Generally, before developing enhancements to this charm, you should consider explaining your use
  case.
- If you would like to chat with us about your use-cases or proposed implementation, you can reach
  us at [Canonical Mattermost public channel](https://chat.charmhub.io/charmhub/channels/charm-dev)
  or [Discourse](https://discourse.charmhub.io/).
- All enhancements require review before being merged. Apart from code quality and test coverage,
  the review will also take into account the resulting user experience for Juju administrators
  using this charm.

## Setup

A typical setup using [snaps](https://snapcraft.io/) can be found in the [Juju
docs](https://juju.is/docs/sdk/dev-setup).

## Developing

You can use the environments created by `tox` for development:

```shell
tox --notest -e unit
source .tox/unit/bin/activate
```

### Testing

```shell
tox -e fmt       # update your code according to linting rules
tox -e lint      # code style
tox -e static    # static analysis
tox -e unit      # unit tests
tox              # runs 'lint', 'static' and 'unit' environments
```

## Build charm

Build the charm in this git repository using:

```shell
charmcraft pack
```
