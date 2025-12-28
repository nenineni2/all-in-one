import pandas as pd
import networkx as nx
from nltk import word_tokenize, pos_tag
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from statistics import mean
import matplotlib.pyplot as plt

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession


# import nltk
# nltk.download("punkt")
# nltk.download("averaged_perceptron_tagger")
# nltk.download("averaged_perceptron_tagger_eng")
# nltk.download("stopwords")
# nltk.download("wordnet")


def extract_svo(sentence: str, stop_words: set, lemmatizer: WordNetLemmatizer):
    tokens = word_tokenize(sentence)
    tagged = pos_tag(tokens)

    # simple subject: first noun (NN, NNP, NNS, NNPS)
    subject = next((w for w, p in tagged if p.startswith("NN")), None)

    # simple verb: first verb (VB*)
    verb_idx = None
    verb = None
    for i, (w, p) in enumerate(tagged):
        if p.startswith("VB"):
            verb = w
            verb_idx = i
            break

    # simple object: first noun after the verb
    target = None
    if verb_idx is not None:
        for w, p in tagged[verb_idx + 1 :]:
            if p.startswith("NN"):
                target = w
                break

    # cleaned / lemmatized relation (verb)
    relation = lemmatizer.lemmatize(verb, "v") if verb else None

    # processed sentence: lower, remove stopwords, lemmatize nouns/verbs
    proc_tokens = []
    for w, p in tagged:
        wl = w.lower()
        if wl.isalnum() and wl not in stop_words:
            pos = "n" if p.startswith("NN") else "v" if p.startswith("VB") else "a"
            proc_tokens.append(lemmatizer.lemmatize(wl, pos))
    processed = " ".join(proc_tokens)

    return subject, target, relation, processed


async def knowledge_graph(
    title: str, sentences: list[str], ctx: Context[ServerSession, None]
) -> pd.DataFrame:
    """Input: list[str] sentences ONLY.
    Output: DataFrame with columns: sentence, source, target, relation, processed_sentence
    """
    await ctx.info("Info: Creating graph")

    stop_words = set(stopwords.words("english"))
    lemmatizer = WordNetLemmatizer()

    plt.figure(figsize=(8, 6))
    plt.clf()

    rows = []
    for s in sentences:
        src, tgt, rel, proc = extract_svo(s, stop_words, lemmatizer)
        rows.append(
            {
                "sentence": s,
                "source": src or "",
                "target": tgt or "",
                "relation": rel or "",
                "processed_sentence": proc,
            }
        )

    pd.set_option("display.max_columns", 250)
    pd.set_option("display.max_colwidth", 250000000)
    df = pd.DataFrame(
        rows,
    )

    await ctx.info("Info: Structuring Data")

    # build directed graph
    G = nx.DiGraph()
    for _, r in df.iterrows():
        src, tgt, rel = r["source"], r["target"], r["relation"]
        if src and tgt:
            G.add_node(src)
            G.add_node(tgt)
            G.add_edge(src, tgt, relation=rel)

    await ctx.info("Info: Computing Nodes")

    # compute node colors (highlight node(s) with max degree)
    if len(G) > 0:
        node_degrees = dict(G.degree)
        node_colors = [
            (
                "lightgreen"
                if node_degrees[n] >= mean(node_degrees.values())
                else "lightblue"
            )
            for n in G.nodes()
        ]

    else:
        node_colors = []

    # positions for layout (caller may visualize using networkx.draw)
    pos = nx.spring_layout(G, seed=42, k=1.5)

    labels = nx.get_edge_attributes(G, "relation")
    nx.draw(
        G,
        pos,
        with_labels=True,
        font_weight="bold",
        node_size=700,
        node_color=node_colors,
        font_size=8,
        arrowsize=10,
    )
    nx.draw_networkx_edge_labels(G, pos, edge_labels=labels, font_size=8)
    plt.title(title)
    await ctx.info("Info: Done!")
    return df
