# mistral (mistral-large-latest) review FAILED

```
HTTP 403 from https://api.mistral.ai/v1/chat/completions: {"object":"error","message":"This model is not available in your subscription tier","type":"tier_not_allowed","param":null,"code":"1910","raw_status_code":403}
```

Common causes: stale model name (override with --model mistral=<name>), bad or expired key, or no network egress to the provider.
