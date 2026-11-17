"""Connector entrypoint for the cg1-ipinfo golden eval connector."""
from connectors.core.connector import Connector, ConnectorError, get_logger

from .operations import check_health, operations

logger = get_logger("cg1-ipinfo")


class CG1IPInfo(Connector):
    def execute(self, config, operation, params, **kwargs):
        handler = operations.get(operation)
        if handler is None:
            raise ConnectorError(f"unknown operation {operation!r}")
        return handler(config, params)

    def check_health(self, config):
        return check_health(config)
