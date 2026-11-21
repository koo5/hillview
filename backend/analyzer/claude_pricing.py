"""Reviewed Haiku Batch usage accounting shared by current and historical runners."""


def batch_price(usage):
    inputs = sum(usage.get(k, 0) for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))
    scale = 5 if inputs > 100000 else 1
    return scale * (.1 * usage.get('input_tokens', 0) + .2 * usage.get('cache_creation_input_tokens', 0)
        + .01 * usage.get('cache_read_input_tokens', 0) + .5 * usage.get('output_tokens', 0)) / 2e6
