# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""COS Tool."""

import logging
import platform
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


class CosTool:
    """Uses cos-tool to inject label matchers into alert rule expressions and validate rules."""

    _path = None
    _disabled = False

    def __init__(self, charm):
        self._charm = charm

    @property
    def path(self):
        """Lazy lookup of the path of cos-tool."""
        if self._disabled:
            return None
        if not self._path:
            self._path = self._get_tool_path()
            if not self._path:
                logger.debug("Skipping injection of juju topology as label matchers")
                self._disabled = True
        return self._path

    def apply_label_matchers(self, rules) -> dict:
        """Will apply label matchers to the expression of all alerts in all supplied groups."""
        if not self.path:
            return rules
        for group in rules["groups"]:
            rules_in_group = group.get("rules", [])
            for rule in rules_in_group:
                topology = {}
                # if the user for some reason has provided juju_unit, we'll need to honor it
                # in most cases, however, this will be empty
                for label in [
                    "juju_model",
                    "juju_model_uuid",
                    "juju_application",
                    "juju_charm",
                    "juju_unit",
                ]:
                    if label in rule["labels"]:
                        topology[label] = rule["labels"][label]

                rule["expr"] = self.inject_label_matchers(rule["expr"], topology)
        return rules

    def validate_alert_rules(self, rules: dict) -> Tuple[bool, str]:
        """Will validate correctness of alert rules, returning a boolean and any errors."""
        if not self.path:
            logger.debug("`cos-tool` unavailable. Not validating alert correctness.")
            return True, ""

        with tempfile.TemporaryDirectory() as tmpdir:
            rule_path = Path(tmpdir + "/validate_rule.yaml")
            rule_path.write_text(yaml.dump(rules))

            args = [str(self.path), "validate", str(rule_path)]
            # noinspection PyBroadException
            try:
                self._exec(args)
                return True, ""
            except subprocess.CalledProcessError as e:
                logger.debug("Validating the rules failed: %s", e.output)
                return False, ", ".join(
                    [
                        line
                        for line in e.output.decode("utf8").splitlines()
                        if "error validating" in line
                    ]
                )

    def inject_label_matchers(self, expression, topology) -> str:
        """Add label matchers to an expression."""
        if not topology:
            return expression
        if not self.path:
            logger.debug("`cos-tool` unavailable. Leaving expression unchanged: %s", expression)
            return expression
        args = [str(self.path), "transform"]
        args.extend(
            ["--label-matcher={}={}".format(key, value) for key, value in topology.items()]
        )

        args.extend(["{}".format(expression)])
        # noinspection PyBroadException
        try:
            return self._exec(args)
        except subprocess.CalledProcessError as e:
            logger.debug('Applying the expression failed: "%s", falling back to the original', e)
            return expression

    def _get_tool_path(self) -> Optional[Path]:
        arch = platform.machine()
        arch = "amd64" if arch == "x86_64" else arch
        res = "cos-tool-{}".format(arch)
        try:
            path = Path(res).resolve()
            path.chmod(0o777)
            return path
        except NotImplementedError:
            logger.debug("System lacks support for chmod")
        except FileNotFoundError:
            logger.debug('Could not locate cos-tool at: "{}"'.format(res))
        return None

    def _exec(self, cmd) -> str:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return result.stdout.decode("utf-8").strip()
