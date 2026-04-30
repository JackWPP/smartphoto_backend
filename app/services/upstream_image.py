"""Upstream Image Generation API — facade for image-generation methods on WhataiClient.

Usage:
    from app.services.upstream_image import WhataiClient
    client = WhataiClient()
    image_bytes = client.generate_image(prompt, ...)
    submissions = client.submit_image_request(prompt, ...)
    results = client.poll_image_tasks(submissions)
    raw_bytes = client.download_image_bytes(url)
"""
from app.services.upstream import WhataiClient

__all__ = ["WhataiClient"]
