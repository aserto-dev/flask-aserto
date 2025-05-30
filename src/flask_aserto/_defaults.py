import re
from dataclasses import dataclass
from typing import Callable, TypeVar, Any

from aserto.client import Identity, ResourceContext
from flask import request

__all__ = [
    "create_default_policy_path_resolver",
    "default_display_state_resource_mapper",
    "default_endpoint_resource_mapper",
]


@dataclass
class Obj:
    object_id: str
    object_type: str


IdentityMapper = Callable[[], Identity]
StringMapper = Callable[[], str]
ObjectMapper = Callable[[], Obj]
ResourceMapper = Callable[[], ResourceContext]
DEFAULT_DISPLAY_STATE_MAP_ENDPOINT = "/__displaystatemap"


@dataclass(frozen=True)
class AuthorizationError(Exception):
    policy_instance_name: str
    policy_path: str


Handler = TypeVar("Handler", bound=Callable[..., Any])


def default_endpoint_resource_mapper() -> ResourceContext:
    return request.view_args or {}


def default_display_state_resource_mapper() -> ResourceContext:
    return request.get_json(silent=True) or {}


def create_default_policy_path_resolver(policy_root: str) -> StringMapper:
    def default_policy_path_resolver() -> str:
        rule_string = str(request.url_rule)
        policy_sub_path = policy_path_heuristic(rule_string)
        return f"{policy_root}.{request.method.upper()}{policy_sub_path}"

    return default_policy_path_resolver


def policy_path_heuristic(path: str) -> str:
    # Replace route arguments surrounded in angle brackets to being
    # prefixed with two underscores, e.g. <id:str> -> __id
    path = re.sub("<([^:]*)(:[^>]*)?>", r"__\1", path)
    path = path.replace("/", ".")
    return path
