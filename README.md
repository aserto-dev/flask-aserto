# Aserto Flask middleware
This is the official library for integrating [Aserto](https://www.aserto.com/) authorization into your [Flask](https://github.com/pallets/flask) applications.

## Aserto Middleware
When authorization middleware is configured and attached to a server, it examines incoming requests, extracts authorization parameters like the caller's identity, calls the Aserto authorizers, and rejects messages if their access is denied.

`AuthorizerOptions` are needed for the cration of an `AsertoMiddleware`.

```py
options = AuthorizerOptions(
        url=authorizer_service_url,
        tenant_id=tenant_id,
        api_key=authorizer_api_key,
        cert_file_path=cert_file_path,
    )
```

To instatiate the middleware, after creating the authorizer's options:

```py
from flask_aserto import AsertoMiddleware, AuthorizationError


app = Flask(__name__)
aserto = AsertoMiddleware(options)

```

Besides the authorizer's options, the following can be configure when creating the middleware:

```py
        authorizer_options: AuthorizerOptions,
        policy_path_root: str,
        identity_provider: IdentityMapper,
        policy_instance_name: Optional[str]= None,
        policy_instance_label: Optional[str]= None,
        policy_path_resolver: Optional[StringMapper] = None,
        resource_context_provider: Optional[ResourceMapper] = None,
```

### Policy
`policy_path_root` is the name of the authorization policy package to evaluate.`policy_instance_name`, `policy_instance_label` are the name and label of the policy that is used by the authorizer.

The authorization policy's ID and the decision to be evaluated are specified when creating authorization Middleware, but the policy path is often derived from the URL or method being called. To provide custom logic, `policy_path_resolver` can be provided. An example can be found
https://github.com/aserto-dev/flask-aserto/tree/HEAD/src/flask_aserto/_defaults.py

### Identity
Middleware offer control over the identity used in authorization calls by providing an `IdentityMapper`. Example of a method that takes the identity from flask's `g` object:

```py
def identity_provider() -> Identity:
    identity = g.identity

    if identity is None:
        return Identity(IdentityType.IDENTITY_TYPE_NONE)

    return Identity(type=IdentityType.IDENTITY_TYPE_SUB, value=identity)
```

### Resource
A resource can be any structured data that the authorization policy uses to evaluate decisions. By default, middleware do not include a resource in authorization calls.

To add resource data, you can provide a `ResourceMapper` to `resource_context_provider` to attach custom logic. For example:

```py
def resource_context_from_request() -> ResourceContext:
    return request.view_args or {}
```

### Add authorization checks to your routes
Below, there is an example of how to add the Middleware to your routes:

```py
from flask_aserto import AsertoMiddleware, AuthorizationError


app = Flask(__name__)
aserto = AsertoMiddleware(**aserto_options)


@app.route("/api/users/<id>", methods=["GET"])
@aserto
def api_user(id: str) -> Response:
    # Raises an AuthorizationError if the `GET.api.users.__id`
    # policy returns a decision of "allowed = false"
    ...
```

## Check Middleware (ReBAC)
In addition to the pattern described above, in which each route is authorized by its own policy module, the middleware can be used to implement Relation-Based Access Control (rebac) in which authorization decisions are made by checking if a given subject has the necessary permission or relation to the object being accessed.

This is achieved using the `Check` function on `AsertoMiddleware`.

A check call needs three pieces of information:
    - The type and key of the object.
    - The name of the relation or permission to look for.
    - The type and key of the subject. When omitted, the subject is derived from the middleware's Identity with type "user".

Example:
```py

def id_mapper() -> str:
    return request.view_args['asset']

@app.route("/resource/<asset>", methods=["GET"])
@requires_auth
@aserto.check(objType="resource", objIdMapper=id_mapper, relationName="can_read")
def get_resource(asset: str):
    return {"message": "Hello from GET /resource/" + asset}

```

GetResource(asset) is an http handler function that serves GET request to the /resource/<asset> route. The `check` call only authorizes requests if the calling user has the `can_read` permission on an object of type resource with the object name extracted from the route's {asset} parameter.

### Check Options
The `check` function accepts options that configure the object, subject, and relation sent to the authorizer.

```py
    def check(
        self,
        objId: Optional[str] = "",
        objType: Optional[str] = "",
        objIdMapper: Optional[StringMapper] = None,
        objMapper: Optional[ObjectMapper] = None,
        relationName: Optional[str] = "",
        relationMapper: Optional[StringMapper] = None,
        subjType: Optional[str] = "",
        subjMapper: Optional[IdentityMapper] = None,
        policyPath: Optional[str] = "",
        policyRoot: Optional[str] = "",
        policyPathMapper: Optional[StringMapper] = None,
```

`subjType` can be used to override `subject_type` in the resource context. If an subject mapper isn't provided, the check call uses the default one which is `user`.

`relationName` sets the relation name sent to the authorizer.

`relationMapper` can be used in cases where the relation to be checked isn't known ahead of time. It receives a function that returns the name of the relation.

`objType` sets the object type sent to the authorizer.

`objId` sets the object ID sent to the authorizer.

`objIdMapper` is used to determine the object ID sent to the authorizer at runtime. It receives a function that returns an object ID.

`objMapper` can be used to set both the object type and ID at runtime. It receives a function that takes returns an `Obj`.

```py
class Obj:
    id: str
    objType: str
```

`policyPath` sets the name of the policy module to evaluate in check calls. It defaults to `check`.

`policyRoot` sets the root of the policy module. For example, if the root is set to "myPolicy", the Check call looks for a policy module named `myPolicy.check`.
