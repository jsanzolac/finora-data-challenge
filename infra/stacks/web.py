"""FinoraDqWeb: private site bucket + CloudFront (OAC). /api/* goes to the HTTP
API (no cache, cookies forwarded, same origin); everything else is the static
export. A CloudFront Function maps clean URLs to the trailingSlash export."""

from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cf
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as deploy
from constructs import Construct

# connect-src adds exactly one host, for the voice analyst (dashboard, NEXT_PUBLIC_VOICE=1):
# @elevenlabs/client 1.36.1 opens a WebSocket to the signed URL from POST /api/agent-session, which is on
# wss://api.elevenlabs.io (non-residency account; WebSocketConnection/location.js). Nothing else is needed:
# - no LiveKit host: WebRTC (wss://livekit.rtc.elevenlabs.io) is not used, the session is websocket-only;
# - no https://api.elevenlabs.io: it is only for sendFeedback, which the dashboard never calls;
# - no blob:/data:/CDN in script-src: the three audio worklets are self-hosted under /voice/ ('self');
# - no media-src: the audio element plays a MediaStream (srcObject), not a URL; no worker-src: no workers.
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' wss://api.elevenlabs.io; "
       "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")

VIEWER_REQUEST = """
var KNOWN = __KNOWN__;
function handler(event) {
  var req = event.request;
  var uri = req.uri;
  var target = uri;
  if (uri.endsWith('/')) { target = uri + 'index.html'; }
  else if (uri.substring(uri.lastIndexOf('/') + 1).indexOf('.') === -1) { target = uri + '/index.html'; }
  if (target.endsWith('.html') && !KNOWN[target]) { target = '/404.html'; }
  req.uri = target;
  return req;
}
"""

VIEWER_RESPONSE = """
function handler(event) {
  var res = event.response;
  if (event.request.uri === '/404.html') { res.statusCode = 404; res.statusDescription = 'Not Found'; }
  return res;
}
"""


def known_pages(web_src: Path) -> str:
    pages = sorted("/" + p.relative_to(web_src).as_posix() for p in web_src.rglob("*.html"))
    return "{" + ",".join(f'"{x}":1' for x in pages) + "}"


class DqWebStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, api, web_src: Path, **kw) -> None:
        super().__init__(scope, cid, **kw)
        site = s3.Bucket(self, "Site", encryption=s3.BucketEncryption.S3_MANAGED,
                         block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                         object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED, enforce_ssl=True,
                         removal_policy=RemovalPolicy.RETAIN)
        headers = cf.ResponseHeadersPolicy(
            self, "SecurityHeaders", response_headers_policy_name="finora-dq-security-headers",
            security_headers_behavior=cf.ResponseSecurityHeadersBehavior(
                content_security_policy=cf.ResponseHeadersContentSecurityPolicy(content_security_policy=CSP,
                                                                                override=True),
                strict_transport_security=cf.ResponseHeadersStrictTransportSecurity(
                    access_control_max_age=Duration.days(365), include_subdomains=True, override=True),
                content_type_options=cf.ResponseHeadersContentTypeOptions(override=True),
                frame_options=cf.ResponseHeadersFrameOptions(frame_option=cf.HeadersFrameOption.DENY, override=True),
                referrer_policy=cf.ResponseHeadersReferrerPolicy(
                    referrer_policy=cf.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN, override=True)))
        # Clean URLs for the trailingSlash export, and 404.html with status 404 for
        # unknown pages. Distribution-wide custom error responses are not used: they
        # would also rewrite the API's JSON 403/404 under /api/* (contract v1).
        fn = cf.Function(self, "CleanUrls", function_name="finora-dq-clean-urls",
                         code=cf.FunctionCode.from_inline(VIEWER_REQUEST.replace("__KNOWN__", known_pages(web_src))),
                         runtime=cf.FunctionRuntime.JS_2_0)
        fn404 = cf.Function(self, "NotFoundStatus", function_name="finora-dq-404-status",
                            code=cf.FunctionCode.from_inline(VIEWER_RESPONSE), runtime=cf.FunctionRuntime.JS_2_0)
        dist = cf.Distribution(
            self, "Dist", comment="Finora DQ dashboard", default_root_object="index.html",
            price_class=cf.PriceClass.PRICE_CLASS_100, minimum_protocol_version=cf.SecurityPolicyProtocol.TLS_V1_2_2021,
            default_behavior=cf.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(site),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cf.CachePolicy.CACHING_OPTIMIZED, response_headers_policy=headers,
                function_associations=[
                    cf.FunctionAssociation(function=fn, event_type=cf.FunctionEventType.VIEWER_REQUEST),
                    cf.FunctionAssociation(function=fn404, event_type=cf.FunctionEventType.VIEWER_RESPONSE)]),
            additional_behaviors={"/api/*": cf.BehaviorOptions(
                origin=origins.HttpOrigin(api.api_domain, protocol_policy=cf.OriginProtocolPolicy.HTTPS_ONLY),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.HTTPS_ONLY,
                allowed_methods=cf.AllowedMethods.ALLOW_ALL, cache_policy=cf.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cf.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                response_headers_policy=headers)})
        # Content-hashed assets are immutable; HTML and the RSC .txt payloads are no-cache.
        static = web_src / "_next" / "static"
        if static.exists():
            deploy.BucketDeployment(self, "StaticAssets", sources=[deploy.Source.asset(str(static))],
                                    destination_bucket=site, destination_key_prefix="_next/static/", prune=False,
                                    memory_limit=512,
                                    cache_control=[deploy.CacheControl.from_string(
                                        "public, max-age=31536000, immutable")])
        deploy.BucketDeployment(self, "Content", sources=[deploy.Source.asset(str(web_src), exclude=["_next/static/*"])],
                                destination_bucket=site, distribution=dist, distribution_paths=["/*"],
                                prune=False, memory_limit=512,
                                cache_control=[deploy.CacheControl.from_string("no-cache")])
        CfnOutput(self, "Url", value=f"https://{dist.distribution_domain_name}")
        CfnOutput(self, "SiteBucket", value=site.bucket_name)
        CfnOutput(self, "WebSource", value=str(web_src.name))
