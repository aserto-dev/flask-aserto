from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Optional, TYPE_CHECKING, Union, cast, overload

from aserto.client import ResourceContext
from flask.wrappers import Response

from ._defaults import (
    AuthorizationError,
    Handler,
    IdentityMapper,
    Obj,
    ObjectMapper,
    ResourceMapper,
    StringMapper,
)

if TYPE_CHECKING:
    from .middleware import AsertoMiddleware


@dataclass(frozen=True)
class CheckOptions:
    """
    Check options class used to create a new instance of Check Middleware
    """

    object_id: str = ""
    object_type: str = ""
    object_id_mapper: Optional[StringMapper] = None
    object_mapper: Optional[ObjectMapper] = None
    relation: str = ""
    relation_mapper: Optional[StringMapper] = None
    subject_type: str = ""
    subject_mapper: Optional[IdentityMapper] = None
    policy_path: str = ""
    policy_root: str = ""
    policy_path_mapper: Optional[StringMapper] = None


def build_resource_context_mapper(opts: CheckOptions) -> ResourceMapper:
    async def resource() -> ResourceContext:
        object_id = opts.object_id if opts.object_id is not None else ""
        object_type = opts.object_type if opts.object_type is not None else ""

        obj = (
            await opts.object_mapper()
            if opts.object_mapper is not None
            else Obj(object_id=object_id, object_type=object_type)
        )

        if opts.object_id_mapper:
            obj.object_id = await opts.object_id_mapper()

        relation = (
            await opts.relation_mapper() if opts.relation_mapper is not None else opts.relation
        )

        subject_type = opts.subject_type if opts.subject_type != "" else "user"

        return {
            "relation": relation,
            "object_type": obj.object_type,
            "object_id": obj.object_id,
            "subject_type": subject_type,
        }

    return resource


class CheckMiddleware:
    def __init__(
        self,
        *,
        options: CheckOptions,
        aserto_middleware: "AsertoMiddleware",
    ):
        self._aserto_middleware = aserto_middleware

        self._identity_provider = (
            options.subject_mapper
            if options.subject_mapper is not None
            else aserto_middleware._identity_provider
        )

        self._resource_context_provider = build_resource_context_mapper(options)
        self._options = options

    def _with_overrides(self, **kwargs: Any) -> "CheckMiddleware":
        return (
            self
            if not kwargs
            else CheckMiddleware(
                aserto_middleware=self._aserto_middleware,
                options=CheckOptions(
                    relation=kwargs.get("relation_name", self._options.relation),
                    relation_mapper=kwargs.get("relation_mapper", self._options.relation_mapper),
                    policy_path=kwargs.get("policy_path", self._options.policy_path),
                    policy_root=kwargs.get("policy_root", self._options.policy_root),
                    subject_mapper=kwargs.get("identity_provider", self._identity_provider),
                    object_id=kwargs.get("object_id", self._options.object_id),
                    object_type=kwargs.get("object_type", self._options.object_type),
                    object_id_mapper=kwargs.get("object_id_mapper", self._options.object_id_mapper),
                    object_mapper=kwargs.get("object_mapper", self._options.object_mapper),
                    subject_type=self._options.subject_type,
                    policy_path_mapper=self._options.policy_path_mapper,
                ),
            )
        )

    def _build_policy_path_mapper(self) -> StringMapper:
        async def mapper() -> str:
            policy_path = ""
            if self._options.policy_path_mapper is not None:
                policy_path = await self._options.policy_path_mapper()
            if policy_path == "":
                policy_path = "check"
                policy_root = self._options.policy_root or self._aserto_middleware._policy_path_root
                if policy_root:
                    policy_path = f"{policy_root}.{policy_path}"
            return policy_path

        return mapper

    @overload
    async def authorize(self, handler: Handler) -> Handler: ...

    @overload
    async def authorize(
        self,
        object_id: str = "",
        object_type: str = "",
        object_id_mapper: Optional[StringMapper] = None,
        object_mapper: Optional[ObjectMapper] = None,
        relation: str = "",
        relation_mapper: Optional[StringMapper] = None,
        subject_type: str = "",
        subject_mapper: Optional[IdentityMapper] = None,
        policy_path: str = "",
        policy_root: str = "",
        policy_path_mapper: Optional[StringMapper] = None,
    ) -> Callable[[Handler], Handler]: ...

    async def authorize(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Union[Handler, Callable[[Handler], Handler]]:
        arguments_error = TypeError(
            f"{self.authorize.__name__}() expects either exactly 1 callable"
            " 'handler' argument or at least 1 'options' argument"
        )

        handler: Optional[Handler] = None

        if not args and kwargs.keys() == {"handler"}:
            handler = kwargs["handler"]
        elif not kwargs and len(args) == 1:
            (handler,) = args

        if handler is not None:
            if not callable(handler):
                raise arguments_error
            return self._authorize(handler)

        if args:
            raise arguments_error

        return self._with_overrides(**kwargs)._authorize

    async def __call__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Union[Handler, Callable[[Handler], Handler]]:
        return await self.authorize(*args, **kwargs)

    def _authorize(self, handler: Handler) -> Handler:
        if self._aserto_middleware._policy_instance_name is None:
            raise TypeError(f"{self._aserto_middleware._policy_instance_name}() should not be None")

        if self._aserto_middleware._policy_instance_label is None:
            self._aserto_middleware._policy_instance_label = (
                self._aserto_middleware._policy_instance_name
            )

        @wraps(handler)
        async def decorated(*args: Any, **kwargs: Any) -> Response:
            policy_mapper = self._build_policy_path_mapper()
            resource_context = await self._resource_context_provider()
            decision = await self._aserto_middleware.is_allowed(
                decision="allowed",
                authorizer_options=self._aserto_middleware._authorizer_options,
                identity_provider=self._identity_provider,
                policy_instance_name=self._aserto_middleware._policy_instance_name or "",
                policy_instance_label=self._aserto_middleware._policy_instance_label or "",
                policy_path_root=self._options.policy_root
                or self._aserto_middleware._policy_path_root,
                policy_path_resolver=policy_mapper,
                resource_context_provider=resource_context,
            )

            if not decision:
                raise AuthorizationError(
                    policy_instance_name=self._aserto_middleware._policy_instance_name or "",
                    policy_path=await policy_mapper(),
                )

            return await handler(*args, **kwargs)

        return cast(Handler, decorated)
