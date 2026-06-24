"""Tiny local fixture site to demo Constructor Scout end-to-end offline.

Serves a deliberately gap-ridden Shopify-style storefront (no autosuggest, no
typo tolerance, no recommendations) so you can see a full prospect brief without
crawling a real site:

    python examples/demo_server.py &           # serves on http://127.0.0.1:8077
    python -m constructor_scout --url http://127.0.0.1:8077 --out demo_out -v
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

HOME = """<!doctype html><html><head>
<script src="https://cdn.shopify.com/s/files/1/theme.js"></script>
<meta property="og:type" content="product"></head><body>
<header><form action="/search" method="get">
  <input type="search" name="q" placeholder="Search our store"></form></header>
<nav>
  <a href="/collections/jackets">Jackets</a>
  <a href="/collections/boots">Boots</a>
  <a href="/collections/backpacks">Backpacks</a>
  <a href="/products/summit-jacket">Summit Jacket</a>
</nav>
<main><h1>Welcome</h1>
<button>Add to cart</button><span itemprop="price">$129.00</span>
</main></body></html>"""

CATEGORY = """<!doctype html><html><body><h1>Jackets</h1>
<ul class="product-grid">
<li class="product-card"><a href="/products/summit-jacket"><img src="/a.jpg">Summit Jacket</a></li>
<li class="product-card"><a href="/products/trail-jacket"><img src="/b.jpg">Trail Jacket</a></li>
<li class="product-card"><a href="/products/rain-jacket"><img src="/c.jpg">Rain Jacket</a></li>
</ul></body></html>"""

PRODUCT = """<!doctype html><html><body>
<h1>Summit Jacket</h1><span itemprop="price">$129.00</span>
<button>Add to cart</button>
<p>A waterproof shell jacket.</p>
</body></html>"""

RESULTS = """<!doctype html><html><body><h2>Results for "{q}"</h2>
<div class="product result"><a href="/products/summit-jacket"><img src="/a.jpg"></a></div>
<div class="product result"><a href="/products/trail-jacket"><img src="/b.jpg"></a></div>
<div class="product result"><a href="/products/rain-jacket"><img src="/c.jpg"></a></div>
</body></html>"""

EMPTY = """<!doctype html><html><body><h2>Search</h2>
<p>No results found. Please try another search.</p></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path, qs = parsed.path, parse_qs(parsed.query)
        if path == "/search":
            q = (qs.get("q", [""])[0]).lower()
            # head term "jacket" and NL "jacket under $50" return products;
            # the misspelling "jackte"/"jacekt" returns nothing (no typo tolerance).
            if "jacket" in q:
                body = RESULTS.format(q=q)
            else:
                body = EMPTY
        elif path.startswith("/collections"):
            body = CATEGORY
        elif path.startswith("/products"):
            body = PRODUCT
        else:
            body = HOME
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8077
    srv = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Demo storefront on http://127.0.0.1:{port} (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
