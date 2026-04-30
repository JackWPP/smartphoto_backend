"""Upstream Analysis API — facade for analysis-related methods on WhataiClient.

Usage:
    from app.services.upstream_analysis import WhataiClient
    client = WhataiClient()
    result = client.analyze_images(...)
    params = client.extract_parameters(...)
    completed = client.complete_parameters(...)
    text_check = client.inspect_visible_text_language(...)
    fidelity_check = client.inspect_image_fidelity(...)
"""
from app.services.upstream import WhataiClient

__all__ = ["WhataiClient"]
