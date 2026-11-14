import json
import urllib.request
import urllib.error
from pathlib import Path

KEY_FILE = Path.home() / ".config/neha-assistant/.env"


def load_tavily_key():
    if not KEY_FILE.exists():
        raise RuntimeError("Neha's .env file was not found.")

    env = {}
    for line in KEY_FILE.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            env[name.strip()] = value.strip()

    key = env.get("TAVILY_API_KEY", "")
    if not key:
        raise RuntimeError("TAVILY_API_KEY is missing from the .env file.")
    return key


def web_search(query, limit=5):
    if not isinstance(query, str) or not query.strip():
        return "Please provide a search query."

    try:
        key = load_tavily_key()
        payload = {
            "api_key": key,
            "query": query.strip(),
            "max_results": max(1, min(int(limit), 10)),
            "search_depth": "basic",
            "include_answer": True
        }

        request = urllib.request.Request(
            "https://api.tavily.com/search",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))

        output = []
        answer = data.get("answer")
        if answer:
            output.append("Summary: " + answer)

        for i, result in enumerate(data.get("results", []), 1):
            output.append(
                f"{i}. {result.get('title', 'Untitled')}\\n"
                f"{result.get('url', '')}\\n"
                f"{result.get('content', '')}"
            )

        return "\\n\\n".join(output) if output else "No search results returned."

    except RuntimeError as error:
        return f"Web search configuration error: {error}"
    except urllib.error.HTTPError as error:
        return f"Web search service returned HTTP {error.code}."
    except urllib.error.URLError:
        return "Could not connect to the web search service. Check your internet connection."
    except (ValueError, TypeError):
        return "The search request or response was invalid."
    except Exception as error:
        return f"Web search failed: {type(error).__name__}."


if __name__ == "__main__":
    query = input("Search the web for: ").strip()
    print(web_search(query))
