import re
import urllib.parse
from io import BytesIO
from typing import Optional, Tuple, Dict
import requests
from PIL import Image
from duckduckgo_search import DDGS
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

class WebService:
    """Handles DuckDuckGo web search, browsing redirects, web image extraction, and Wikipedia fallbacks."""

    KNOWN_SERVICES: Dict[str, Tuple[str, str, Optional[str]]] = {
        'youtube': ('YouTube', 'https://www.youtube.com', 'https://www.youtube.com/results?search_query='),
        'yt': ('YouTube', 'https://www.youtube.com', 'https://www.youtube.com/results?search_query='),
        'google': ('Google Search', 'https://www.google.com', 'https://www.google.com/search?q='),
        'github': ('GitHub', 'https://github.com', 'https://github.com/search?q='),
        'wikipedia': ('Wikipedia', 'https://www.wikipedia.org', 'https://en.wikipedia.org/wiki/Special:Search?search='),
        'wiki': ('Wikipedia', 'https://www.wikipedia.org', 'https://en.wikipedia.org/wiki/Special:Search?search='),
        'reddit': ('Reddit', 'https://www.reddit.com', 'https://www.reddit.com/search/?q='),
        'amazon': ('Amazon', 'https://www.amazon.com', 'https://www.amazon.com/s?k='),
        'chatgpt': ('ChatGPT', 'https://chatgpt.com', None),
        'claude': ('Claude AI', 'https://claude.ai', None),
        'gemini': ('Google Gemini', 'https://gemini.google.com', None),
        'openai': ('OpenAI', 'https://openai.com', None),
        'twitter': ('X / Twitter', 'https://x.com', 'https://x.com/search?q='),
        'x': ('X / Twitter', 'https://x.com', 'https://x.com/search?q='),
        'linkedin': ('LinkedIn', 'https://www.linkedin.com', 'https://www.linkedin.com/search/results/all/?keywords='),
        'stackoverflow': ('Stack Overflow', 'https://stackoverflow.com', 'https://stackoverflow.com/search?q='),
        'netflix': ('Netflix', 'https://www.netflix.com', 'https://www.netflix.com/search?q='),
        'spotify': ('Spotify', 'https://open.spotify.com', 'https://open.spotify.com/search/'),
        'gmail': ('Gmail', 'https://mail.google.com', None),
        'maps': ('Google Maps', 'https://maps.google.com', 'https://www.google.com/maps/search/'),
        'huggingface': ('Hugging Face', 'https://huggingface.co', 'https://huggingface.co/models?search='),
        'kaggle': ('Kaggle', 'https://www.kaggle.com', 'https://www.kaggle.com/search?q='),
        'discord': ('Discord', 'https://discord.com', None),
        'twitch': ('Twitch', 'https://www.twitch.tv', 'https://www.twitch.tv/search?term='),
        'instagram': ('Instagram', 'https://www.instagram.com', None),
        'facebook': ('Facebook', 'https://www.facebook.com', None),
        'whatsapp': ('WhatsApp Web', 'https://web.whatsapp.com', None),
        'pinterest': ('Pinterest', 'https://www.pinterest.com', 'https://www.pinterest.com/search/pins/?q='),
        'notion': ('Notion', 'https://www.notion.so', None),
        'canva': ('Canva', 'https://www.canva.com', None),
        'figma': ('Figma', 'https://www.figma.com', None),
        'bing': ('Bing Search', 'https://www.bing.com', 'https://www.bing.com/search?q='),
        'duckduckgo': ('DuckDuckGo', 'https://duckduckgo.com', 'https://duckduckgo.com/?q='),
        'medium': ('Medium', 'https://medium.com', 'https://medium.com/search?q='),
        'quora': ('Quora', 'https://www.quora.com', 'https://www.quora.com/search?q=')
    }

    TLD_PATTERN = r'\.(com|org|net|io|ai|co|in|edu|gov|dev|app|me|tech|info|xyz|so|tv|cc|to|uk|ca|de|jp|us|fr|au|site|store|online|live|club|pro)(/.*)?$'

    def __init__(self, max_results: int = 4):
        self.max_results = max_results
        try:
            self.search_wrapper = DuckDuckGoSearchAPIWrapper(max_results=max_results)
        except Exception:
            self.search_wrapper = None
        try:
            import wikipedia
            wikipedia.set_user_agent("SearchStudioApp/2.0 (contact: support@searchstudio.ai)")
        except Exception:
            pass

    def resolve_browsing_intent(self, query: str) -> Optional[Tuple[str, str]]:
        """
        Detects if query is a URL, domain, or browsing/navigation intent.
        Returns: (target_url, display_title) or None
        """
        q = query.strip()
        if not q:
            return None

        lower = q.lower()

        # 1. Direct explicit URL
        if lower.startswith(('http://', 'https://', 'ftp://')):
            return q, q

        # 2. Starts with www.
        if lower.startswith('www.') and len(lower) > 4:
            return f'https://{q}', q

        # 3. Single token domain (e.g. youtube.com, github.io/repo)
        if ' ' not in q and re.search(self.TLD_PATTERN, lower):
            return f'https://{q}', q

        # 4. Navigation command prefixes
        prefixes = [
            'open website ', 'open site ', 'open link ', 'open page ',
            'open url ', 'open ', 'launch ', 'go to ', 'visit ',
            'browse to ', 'browse ', 'navigate to ', 'take me to ',
            'search google for ', 'google for ', 'google ',
            'search on google for ', 'search on google ',
            'search on youtube for ', 'search on youtube ', 'search youtube for ',
            'play ', 'watch ', 'listen to '
        ]

        matched_prefix = None
        for p in prefixes:
            if lower.startswith(p):
                matched_prefix = p
                break

        if matched_prefix:
            remainder = q[len(matched_prefix):].strip()
            rem_lower = remainder.lower()

            # Check specific search engine triggers
            if matched_prefix in ['search google for ', 'google for ', 'google ', 'search on google for ', 'search on google ']:
                return f'https://www.google.com/search?q={urllib.parse.quote(remainder)}', f'Google Search: "{remainder}"'

            if matched_prefix in ['play ', 'watch ', 'listen to ', 'search on youtube for ', 'search on youtube ', 'search youtube for ']:
                return f'https://www.youtube.com/results?search_query={urllib.parse.quote(remainder)}', f'YouTube: "{remainder}"'

            # Check if remainder is a direct domain
            if re.search(self.TLD_PATTERN, rem_lower):
                url = remainder if remainder.startswith(('http://', 'https://')) else f'https://{remainder}'
                return url, remainder

            # Check known services with search queries
            for svc_key, (name, base_url, search_url) in self.KNOWN_SERVICES.items():
                if rem_lower == svc_key:
                    return base_url, name

                for prep in [' for ', ' search ', ' search for ', ' on ']:
                    if rem_lower.startswith(svc_key + prep):
                        term = remainder[len(svc_key + prep):].strip()
                        if term and search_url:
                            return f'{search_url}{urllib.parse.quote(term)}', f'{name}: "{term}"'
                        elif base_url:
                            return base_url, name

            # If user said 'open <known-service>'
            if rem_lower in self.KNOWN_SERVICES:
                name, base_url, _ = self.KNOWN_SERVICES[rem_lower]
                return base_url, name

            # If user said 'open <service>.com'
            domain_match = re.match(r'^([a-zA-Z0-9-]+)\.(com|org|net|io|ai|co|in|edu|gov|dev|app|me|tech|info|xyz|so|tv|cc|to)(/.*)?$', rem_lower)
            if domain_match:
                return f'https://{remainder}', remainder

            # If user said 'open <something>' where <something> is a clean alphanumeric name
            if ' ' not in rem_lower and re.match(r'^[a-zA-Z0-9\-]+$', rem_lower):
                return f'https://www.{rem_lower}.com', f'{remainder.capitalize()}'

        return None

    def search_text(self, query: str) -> str:
        """Runs a live web search query and returns formatted text summaries with fallback."""
        # Attempt 1: LangChain DDG Wrapper
        if self.search_wrapper:
            try:
                results = self.search_wrapper.run(query)
                if results and results.strip() and not results.startswith("DuckDuckGo was unable"):
                    return results
            except Exception:
                pass

        # Attempt 2: Direct DDGS text search
        try:
            with DDGS() as ddgs:
                ddgs_results = list(ddgs.text(query, max_results=self.max_results))
                if ddgs_results:
                    formatted = []
                    for r in ddgs_results:
                        formatted.append(f"Title: {r.get('title','')}\nSnippet: {r.get('body','')}\nURL: {r.get('href','')}")
                    return "\n\n".join(formatted)
        except Exception:
            pass

        # Attempt 3: Wikipedia Summary Fallback
        try:
            import wikipedia
            titles = wikipedia.search(query, results=2)
            if titles:
                summary = wikipedia.summary(titles[0], sentences=4)
                return f"Source (Wikipedia - {titles[0]}):\n{summary}"
        except Exception:
            pass

        return f"Live search results for: '{query}' (No specific web pages could be fetched at this time)."

    def fetch_web_image(self, query: str) -> Tuple[Optional[Image.Image], Optional[str], Optional[str]]:
        """
        Attempts to search and download a high-res image for a query.
        Returns: (PIL.Image or None, source_url or None, error_message or None)
        """
        image_url = None
        source_desc = None

        # Clean query if user typed "picture of xyz"
        clean_query = query.lower()
        for prefix in ["picture of ", "photo of ", "image of ", "pic of ", "show me ", "diagram of ", "draw ", "generate image of ", "generate image "]:
            if clean_query.startswith(prefix):
                clean_query = clean_query[len(prefix):].strip()
                break

        # Attempt 1: DuckDuckGo Image Search
        try:
            with DDGS() as ddgs:
                results = list(ddgs.images(clean_query, max_results=3))
                if results:
                    for r in results:
                        candidate_url = r.get("image")
                        if candidate_url and not candidate_url.endswith(".svg"):
                            image_url = candidate_url
                            source_desc = r.get("title", clean_query)
                            break
        except Exception:
            pass

        # Attempt 2: Wikipedia Fallback
        if not image_url:
            try:
                import wikipedia
                page_titles = wikipedia.search(clean_query, results=2)
                if page_titles:
                    page = wikipedia.page(page_titles[0], auto_suggest=False)
                    for img in page.images:
                        if not img.lower().endswith(('.svg', '.gif')):
                            image_url = img
                            source_desc = f"Wikipedia: {page.title}"
                            break
            except Exception:
                pass

        if not image_url:
            return None, None, f"No suitable images found for query '{clean_query}'"

        # Download image payload
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            resp = requests.get(image_url, headers=headers, timeout=10)
            resp.raise_for_status()
            img = Image.open(BytesIO(resp.content))
            return img, image_url, None
        except Exception as e:
            return None, image_url, f"Failed downloading image: {e}"
