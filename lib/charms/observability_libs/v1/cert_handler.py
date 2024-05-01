# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
"""## Overview.

This document explains how to use the `CertHandler` class to
create and manage TLS certificates through the `tls_certificates` interface.

The goal of the CertHandler is to provide a wrapper to the `tls_certificates`
library functions to make the charm integration smoother.

## Library Usage

This library should be used to create a `CertHandler` object, as per the
following example:

```python
self.cert_handler = CertHandler(
    charm=self,
    key="my-app-cert-manager",
    cert_subject="unit_name",  # Optional
)
```

You can then observe the library's custom event and make use of the key and cert:
```python
self.framework.observe(self.cert_handler.on.cert_changed, self._on_server_cert_changed)

container.push(keypath, self.cert_handler.private_key)
container.push(certpath, self.cert_handler.servert_cert)
```

Since this library uses [Juju Secrets](https://juju.is/docs/juju/secret) it requires Juju >= 3.0.3.
"""
import abc
import ipaddress
import json
import socket
from itertools import filterfalse
from typing import Dict, List, Optional, Union

try:
    from charms.tls_certificates_interface.v3.tls_certificates import (  # type: ignore
        AllCertificatesInvalidatedEvent,
        CertificateAvailableEvent,
        CertificateExpiringEvent,
        CertificateInvalidatedEvent,
        ProviderCertificate,
        TLSCertificatesRequiresV3,
        generate_csr,
        generate_private_key,
    )
except ImportError as e:
    raise ImportError(
        "failed to import charms.tls_certificates_interface.v2.tls_certificates; "
        "Either the library itself is missing (please get it through charmcraft fetch-lib) "
        "or one of its dependencies is unmet."
    ) from e

import logging

from ops.charm import CharmBase, RelationBrokenEvent
from ops.framework import EventBase, EventSource, Object, ObjectEvents
from ops.jujuversion import JujuVersion
from ops.model import Relation, Secret, SecretNotFoundError

logger = logging.getLogger(__name__)

LIBID = "b5cd5cd580f3428fa5f59a8876dcbe6a"
LIBAPI = 1
LIBPATCH = 7


def is_ip_address(value: str) -> bool:
    """Return True if the input value is a valid IPv4 address; False otherwise."""
    try:
        ipaddress.IPv4Address(value)
        return True
    except ipaddress.AddressValueError:
        return False


class CertChanged(EventBase):
    """Event raised when a cert is changed (becomes available or revoked)."""


class CertHandlerEvents(ObjectEvents):
    """Events for CertHandler."""

    cert_changed = EventSource(CertChanged)


class _VaultBackend(abc.ABC):
    def store(self, contents: Dict[str, str], clear: bool = False): ...

    def get_value(self, key: str) -> Optional[str]: ...

    def retrieve(self) -> Dict[str, str]: ...

    def nuke(self): ...


class _RelationVaultBackend(_VaultBackend):
    """Relation backend for Vault.

    Use it to store data in a relation databag.
    Assumes that a single relation exists and its data is readable.
    If not, it will raise RuntimeErrors as soon as you try to read/write.
    It will store the data, in plaintext (json-dumped) nested under a configurable
    key in the **unit databag** of this relation.
    """

    def __init__(self, charm: CharmBase, relation_name: str, nest_under: str = "secret-contents"):
        self.charm = charm
        self.relation_name = relation_name
        self.nest_under = nest_under  # needs to be charm-unique.

    def _check_ready(self):
        try:
            self.charm.model.get_relation(self.relation_name).data[self.charm.unit]   # pyright: ignore
        except Exception as e:
            # if something goes wrong here, the peer-backed vault is not ready to operate
            # it can be because you are trying to use it too soon, i.e. before the peer
            # relation has been created (or has joined).
            raise RuntimeError(" backend not ready.") from e

    @property
    def _relation(self) -> Optional[Relation]:
        self._check_ready()
        return self.charm.model.get_relation(self.relation_name)

    @property
    def _databag(self):
        self._check_ready()
        return self._relation.data[self.charm.unit]  # pyright: ignore

    def _read(self) -> Dict[str, str]:
        value = self._databag.get(self.nest_under)
        if value:
            return json.loads(value)
        return {}

    def _write(self, value: Dict[str, str]):
        if not all(isinstance(x, str) for x in value.values()):
            # the caller has to take care of encoding
            raise TypeError("You can only store strings in Vault.")

        self._databag[self.nest_under] = json.dumps(value)

    def store(self, contents: Dict[str, str], clear: bool = False):
        """Create a new revision by updating the previous one with ``contents``."""
        current = self._read()

        if clear:
            current.clear()

        current.update(contents)
        self._write(current)

    def get_value(self, key: str):
        """Like retrieve, but single-value."""
        return self._read().get(key)

    def retrieve(self):
        """Return the full vault content."""
        return self._read()

    def nuke(self):
        del self._databag[self.nest_under]


class _SecretVaultBackend(_VaultBackend):
    """Relation backend for Vault.

    Use it to store data in a Juju secret.
    Assumes that Juju supports secrets.
    If not, it will raise some exception as soon as you try to read/write.
    """

    _uninitialized_key = "uninitialized-secret-key"

    def __init__(self, charm: CharmBase, label: str):
        self.charm = charm
        self.label = label  # needs to be charm-unique.

    @property
    def _secret(self) -> Secret:
        try:
            # we are owners, so we don't need to grant it to ourselves
            return self.charm.model.get_secret(label=self.label)
        except SecretNotFoundError:
            # we need to set SOME contents when we're creating the secret, so we do it.
            return self.charm.app.add_secret({self._uninitialized_key: "42"}, label=self.label)

    def store(self, contents: Dict[str, str], clear: bool = False):
        """Create a new revision by updating the previous one with ``contents``."""
        secret = self._secret
        current = secret.get_content(refresh=True)

        if clear:
            current.clear()
        elif current.get(self._uninitialized_key):
            # is this the first revision? clean up the dummy contents we created instants ago.
            del current[self._uninitialized_key]

        current.update(contents)
        secret.set_content(current)

    def get_value(self, key):
        """Like retrieve, but single-value."""
        return self._secret.get_content(refresh=True).get(key)

    def retrieve(self):
        """Return the full vault content."""
        return self._secret.get_content(refresh=True)

    def nuke(self):
        self._secret.remove_all_revisions()


class Vault:
    """Simple application secret wrapper for local usage."""

    def __init__(self, backend: _VaultBackend):
        self._backend = backend

    def store(self, contents: Dict[str, str], clear: bool = False):
        """Store these contents in the vault overriding whatever is there."""
        self._backend.store(contents, clear=clear)

    def get_value(self, key: str):
        """Like retrieve, but single-value."""
        return self._backend.get_value(key)

    def retrieve(self) -> Dict[str, str]:
        """Return the full vault content."""
        return self._backend.retrieve()

    def nuke(self):
        """Clear the vault."""
        self._backend.nuke()


class CertHandler(Object):
    """A wrapper for the requirer side of the TLS Certificates charm library."""

    on = CertHandlerEvents()  # pyright: ignore

    def __init__(
        self,
        charm: CharmBase,
        *,
        key: str,
        certificates_relation_name: str = "certificates",
        cert_subject: Optional[str] = None,
        sans: Optional[List[str]] = None,
    ):
        """CertHandler is used to wrap TLS Certificates management operations for charms.

        CerHandler manages one single cert.

        Args:
            charm: The owning charm.
            key: A manually-crafted, static, unique identifier used by ops to identify events.
             It shouldn't change between one event to another.
            certificates_relation_name: Must match metadata.yaml.
            cert_subject: Custom subject. Name collisions are under the caller's responsibility.
            sans: DNS names. If none are given, use FQDN.
        """
        super().__init__(charm, key)
        self.charm = charm

        # We need to sanitize the unit name, otherwise route53 complains:
        # "urn:ietf:params:acme:error:malformed" :: Domain name contains an invalid character
        self.cert_subject = charm.unit.name.replace("/", "-") if not cert_subject else cert_subject

        # Use fqdn only if no SANs were given, and drop empty/duplicate SANs
        sans = list(set(filter(None, (sans or [socket.getfqdn()]))))
        self.sans_ip = list(filter(is_ip_address, sans))
        self.sans_dns = list(filterfalse(is_ip_address, sans))

        if self._check_juju_supports_secrets():
            vault_backend = _SecretVaultBackend(charm, label="cert-handler-private-vault")

            # TODO: gracefully handle situations where the
            #  secret is gone because the admin has removed it manually
            # self.framework.observe(self.charm.on.secret_remove, self._rotate_csr)

        else:
            vault_backend = _RelationVaultBackend(charm, relation_name="peers")
        self.vault = Vault(vault_backend)

        self.certificates_relation_name = certificates_relation_name
        self.certificates = TLSCertificatesRequiresV3(self.charm, self.certificates_relation_name)

        self.framework.observe(
            self.charm.on.config_changed,
            self._on_config_changed,
        )
        self.framework.observe(
            self.charm.on[self.certificates_relation_name].relation_joined,  # pyright: ignore
            self._on_certificates_relation_joined,
        )
        self.framework.observe(
            self.certificates.on.certificate_available,  # pyright: ignore
            self._on_certificate_available,
        )
        self.framework.observe(
            self.certificates.on.certificate_expiring,  # pyright: ignore
            self._on_certificate_expiring,
        )
        self.framework.observe(
            self.certificates.on.certificate_invalidated,  # pyright: ignore
            self._on_certificate_invalidated,
        )
        self.framework.observe(
            self.certificates.on.all_certificates_invalidated,  # pyright: ignore
            self._on_all_certificates_invalidated,
        )
        self.framework.observe(
            self.charm.on[self.certificates_relation_name].relation_broken,  # pyright: ignore
            self._on_certificates_relation_broken,
        )
        self.framework.observe(
            self.charm.on.upgrade_charm,  # pyright: ignore
            self._on_upgrade_charm,
        )

    def _on_upgrade_charm(self, _):
        self._migrate_vault()

    def _migrate_vault(self):
        peer_backend = _RelationVaultBackend(self.charm, relation_name="peers")

        if self._check_juju_supports_secrets():
            # we are on recent juju
            if self.vault.retrieve():
                # we already were on recent juju: nothing to migrate
                return

            # we used to be on old juju: our secret stuff is in peer data
            if peer_backend.retrieve():
                # move over to secret-backed storage
                self.vault.store(peer_backend.retrieve())

                # clear the peer storage
                peer_backend.nuke()
                return

        # if we are downgrading, i.e. from juju with secrets to juju without,
        # we have lost all that was in the secrets backend.

    @property
    def enabled(self) -> bool:
        """Boolean indicating whether the charm has a tls_certificates relation."""
        # We need to check for units as a temporary workaround because of https://bugs.launchpad.net/juju/+bug/2024583
        # This could in theory not work correctly on scale down to 0 but it is necessary for the moment.

        if not self.charm.model.get_relation(self.certificates_relation_name):
            return False

        if not self.charm.model.get_relation(
            self.certificates_relation_name
        ).units:  # pyright: ignore
            return False

        if not self.charm.model.get_relation(
            self.certificates_relation_name
        ).app:  # pyright: ignore
            return False

        if not self.charm.model.get_relation(
            self.certificates_relation_name
        ).data:  # pyright: ignore
            return False

        return True

    def _on_certificates_relation_joined(self, _) -> None:
        if not self._csr:
            self._generate_csr()

    def _on_config_changed(self, _):
        relation = self.charm.model.get_relation(self.certificates_relation_name)

        if not relation:
            return

        self._generate_csr(renew=True)

    @property
    def relation(self):
        """The "certificates" relation."""
        return self.charm.model.get_relation(self.certificates_relation_name)

    def _generate_csr(
        self, overwrite: bool = False, renew: bool = False, clear_cert: bool = False
    ):
        """Request a CSR "creation" if renew is False, otherwise request a renewal.

        Without overwrite=True, the CSR would be created only once, even if calling the method
        multiple times. This is useful needed because the order of peer-created and
        certificates-joined is not predictable.

        This method intentionally does not emit any events, leave it for caller's responsibility.
        """
        # if we are in a relation-broken hook, we might not have a relation to publish the csr to.
        if not self.relation:
            logger.warning(
                f"No {self.certificates_relation_name!r} relation found. " f"Cannot generate csr."
            )
            return

        # In case we already have a csr, do not overwrite it by default.
        if overwrite or renew or not self._csr:
            private_key = self.private_key
            if private_key is None:
                # FIXME: raise this in a less nested scope by
                #  generating privkey and csr in the same method.
                raise RuntimeError(
                    "private key unset. call _generate_privkey() before you call this method."
                )
            csr = generate_csr(
                private_key=private_key.encode(),
                subject=self.cert_subject,
                sans_dns=self.sans_dns,
                sans_ip=self.sans_ip,
            )

            if renew and self._csr:
                self.certificates.request_certificate_renewal(
                    old_certificate_signing_request=self._csr.encode(),
                    new_certificate_signing_request=csr,
                )
            else:
                logger.info(
                    "Creating CSR for %s with DNS %s and IPs %s",
                    self.cert_subject,
                    self.sans_dns,
                    self.sans_ip,
                )
                self.certificates.request_certificate_creation(certificate_signing_request=csr)

        if clear_cert:
            self.vault.nuke()

    def _on_certificate_available(self, event: CertificateAvailableEvent) -> None:
        """Emit cert-changed."""
        self.on.cert_changed.emit()  # pyright: ignore

    @property
    def private_key(self) -> Optional[str]:
        """Private key.

        BEWARE: if the vault misbehaves, the backing secret is removed, the peer relation dies
        or whatever, we might be calling generate_private_key() again and cause a desync
        with the CSR because it's going to be signed with an outdated key we have no way of retrieving.
        The caller needs to ensure that if the vault backend gets reset, then so does the csr.

        TODO: we could consider adding a way to verify if the csr was signed by our privkey,
            and do that on collect_unit_status as a sanity check
        """
        private_key = self.vault.get_value("private-key")
        if private_key is None:
            private_key = generate_private_key().decode()
            self.vault.store({"private-key": private_key})
        return private_key

    @property
    def _csr(self) -> Optional[str]:
        csrs = self.certificates.get_requirer_csrs()
        if not csrs:
            return None
        return csrs[-1].csr

    def get_cert(self) -> ProviderCertificate:
        """Get cert."""
        all_certs = self.certificates.get_provider_certificates()
        return [c for c in all_certs if c.csr == self._csr][0]

    @property
    def ca_cert(self) -> Optional[str]:
        """CA Certificate."""
        return self.get_cert().ca

    @property
    def server_cert(self) -> Optional[str]:
        """Server Certificate."""
        return self.get_cert().certificate

    @property
    def chain(self) -> Optional[str]:
        """Return the ca chain."""
        return self.get_cert().chain_as_pem()

    def _on_certificate_expiring(
        self, event: Union[CertificateExpiringEvent, CertificateInvalidatedEvent]
    ) -> None:
        """Generate a new CSR and request certificate renewal."""
        if event.certificate == self.server_cert:
            self._generate_csr(renew=True)

    def _certificate_revoked(self, event) -> None:
        """Remove the certificate and generate a new CSR."""
        # Note: assuming "limit: 1" in metadata
        if event.certificate == self.server_cert:
            self._generate_csr(overwrite=True, clear_cert=True)
            self.on.cert_changed.emit()  # pyright: ignore

    def _on_certificate_invalidated(self, event: CertificateInvalidatedEvent) -> None:
        """Deal with certificate revocation and expiration."""
        if event.certificate != self.server_cert:
            return

        # if event.reason in ("revoked", "expired"):
        # Currently, the reason does not matter to us because the action is the same.
        self._generate_csr(overwrite=True, clear_cert=True)
        self.on.cert_changed.emit()  # pyright: ignore

    def _on_all_certificates_invalidated(self, _: AllCertificatesInvalidatedEvent) -> None:
        # Do what you want with this information, probably remove all certificates
        # Note: assuming "limit: 1" in metadata
        self._generate_csr(overwrite=True, clear_cert=True)
        self.on.cert_changed.emit()  # pyright: ignore

    def _on_certificates_relation_broken(self, _: RelationBrokenEvent) -> None:
        """Clear all secrets data when removing the relation."""
        self.vault.nuke()
        self.on.cert_changed.emit()  # pyright: ignore

    def _check_juju_supports_secrets(self) -> bool:
        version = JujuVersion.from_environ()

        if not JujuVersion(version=str(version)).has_secrets:
            msg = f"Juju version {version} does not supports Secrets. Juju >= 3.0.3 is needed"
            logger.error(msg)
            return False
        return True
