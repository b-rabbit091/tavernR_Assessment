import wikipedia # https://wikipedia.readthedocs.io/en/latest/code.html#api
import json
import sqlite3
import spacy
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import re


_META_PAGE_PATTERN = re.compile(
    r'disambiguation|wikidata|short description|wikipedia:|cs1|'
    r'^use |^articles |^pages |^all articles',
    re.IGNORECASE
)

# Load spacy model once at module level
nlp = spacy.load("en_core_web_sm")

# create the database if it doesn't exist
conn = sqlite3.connect("pages.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS pages (name TEXT, links TEXT)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_pages_name ON pages (name)")
conn.commit()

def encode_texts_batch(texts):
    """Batch encode multiple texts in a single spacy pass for efficiency"""
    docs = list(nlp.pipe(texts))
    return np.array([doc.vector for doc in docs]).reshape(len(docs), -1)

def encode_text(text):
    """Encode text using spacy's sentence vectors"""
    doc = nlp(text)
    return doc.vector.reshape(1, -1)

def get_page(page_name):
    """Get a specific Wikipedia page by name"""
    try:
        return wikipedia.page(page_name, auto_suggest=False, redirect=False)
    except wikipedia.exceptions.DisambiguationError as e:
        return wikipedia.page(e.options[0], auto_suggest=False, redirect=False)
    except wikipedia.exceptions.PageError:
        pass

    try:
        search_results = wikipedia.search(page_name)
        choice = search_results[0]
        page = wikipedia.page(choice, auto_suggest=False, redirect=False)
        return page
    except Exception:
        # Return a default page if not found
        return wikipedia.page("Python (programming language)")

def get_page_links_with_cache(page_name):

    cached_page = cursor.execute("SELECT * FROM pages WHERE name = ?", (page_name,)).fetchone()

    if not cached_page:
        page = get_page(page_name)
        links = page.links
        categories = page.categories
        cursor.execute("INSERT INTO pages (name, links) VALUES (?, ?)", (page_name, json.dumps(links + categories)))
        conn.commit()
        cached_page = cursor.execute("SELECT * FROM pages WHERE name = ?", (page_name,)).fetchone()

    links = json.loads(cached_page[1])
    filtered = [link for link in links if is_regular_page(link)]
    if page_name in filtered:
        filtered.remove(page_name)
    return filtered

def is_regular_page(page_name):
    return not _META_PAGE_PATTERN.search(page_name)

# TODO: Gotta speed this up. It's OK if we don't get the shortest path, but we should get *a* path.
def _find_short_path(start_path, end_path):
    """Quick and dirty method to find a short path between two Wikipedia pages. Hill climbs from the start and end pages towards each other, using cosine similarity of sentence embeddings to score links. Kinda like A*, but with cosine similarity instead of Euclidean distance?"""

    start_leaf = start_path[-1]
    end_leaf = end_path[0]

    if len(start_path) + len(end_path) > 20:
        return None

    if start_leaf == end_leaf:
        return start_path + end_path[1:]

    links = get_page_links_with_cache(start_leaf)
    if end_leaf in links:
        return start_path + end_path

    backlinks = get_page_links_with_cache(end_leaf)

    intersection = list(set(links) & set(backlinks))
    if len(intersection) > 0:
        return start_path + [intersection[0]] + end_path
    print(f"{start_path[-1]} ??? {end_path[0]}")

    if not links or not backlinks:
        return None

    visited = set(start_path + end_path)

    end_leaf_page = get_page(end_leaf)
    end_embedding = encode_text(end_leaf_page.summary)
    link_vectors = encode_texts_batch(links)
    scores = cosine_similarity(link_vectors, end_embedding).flatten()
    scored_links = sorted(zip(links, scores), key=lambda x: x[1], reverse=True)
    next_page = next((link for link, _ in scored_links if link not in visited), None)
    if next_page is None:
        return None


    start_leaf_page = get_page(start_leaf)
    start_embedding = encode_text(start_leaf_page.summary)
    backlink_vectors = encode_texts_batch(backlinks)
    scores = cosine_similarity(backlink_vectors, start_embedding).flatten()
    scored_categories = sorted(zip(backlinks, scores), key=lambda x: x[1], reverse=True)
    previous_page = next((link for link, _ in scored_categories if link not in visited), None)
    if previous_page is None:
        return None

    return _find_short_path(start_path + [next_page], [previous_page] + end_path)

def find_short_path(start_page, end_page):
    start_path = [start_page.title]
    end_path = [end_page.title]

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_find_short_path, start_path, end_path)
        try:
            return future.result(timeout=10)
        except FuturesTimeoutError:
            return None