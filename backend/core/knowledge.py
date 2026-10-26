"""Small, dependency-free helpers for offline knowledge extraction.

The production extractor can use an LLM, but the local fallback still needs
to return a useful graph when no provider is configured.  The rules here are
deliberately conservative: headings, known technical phrases and high-value
technical nouns are kept, while ordinary English grammar words are ignored.
Explicit prerequisite wording is used to orient edges as ``prerequisite ->
dependent``.
"""

from __future__ import annotations

import re
import unicodedata


# A token may contain the punctuation commonly used by technical names:
# ``C++``, ``C#``, ``self-attention``, ``QKV`` and ``BERT-base``.
_TERM = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[_+#./-][A-Za-z0-9_+#./-]*)*|[\u3400-\u9fff]+")
_EN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[_+#./-][A-Za-z0-9_+#./-]*)*")
_ZH_SPAN = re.compile(r"[\u3400-\u9fff]+")
_MD_HEADING = re.compile(r"(?m)^[ \t]{0,3}(#{1,6})[ \t]+(.+?)\s*#*\s*$")
# PDF extractors usually keep numbered section titles but drop Markdown
# markers.  Recover those levels so paper structure can contribute reliable
# prerequisite edges.
_NUMBERED_HEADING = re.compile(
    r"(?m)^\s*(?P<number>\d+(?:\.\d+){0,4})\s+(?P<title>[A-Z][^\n]{2,120}?)\s*$"
)

_PAPER_SINGLE_TERMS = {
    "attention", "transformer", "encoder", "decoder", "embedding", "embeddings", "softmax",
    "positional", "encoding", "recurrent", "convolution", "convolutional", "parallelization",
    "autoregressive", "representation", "training", "optimizer", "adam", "regularization", "dropout",
    "bleu", "wmt", "gpu", "gpus", "wordpiece", "wordpieces", "parsing", "sequence", "sequences",
    "transduction", "query", "queries", "key", "keys", "value", "values", "residual", "normalization",
    "evaluation", "accuracy", "precision", "recall", "dataset", "datasets", "tokens", "tokenization",
    "heads", "head", "beam", "search", "data", "model", "models", "translation", "architecture",
}


# Function words and relation cues must never become concepts.  Keeping this
# list explicit makes the fallback predictable and easy to extend.
_STOP_WORDS = {
    "a", "an", "the", "this", "that", "these", "those", "it", "its",
    "they", "their", "them", "we", "our", "ours", "you", "your", "yours",
    "he", "she", "his", "her", "who", "what", "which", "whose", "there",
    "is", "are", "was", "were", "be", "been", "being", "am", "do", "does",
    "did", "done", "has", "have", "had", "having", "can", "could", "may",
    "might", "must", "shall", "should", "will", "would", "and", "or", "but",
    "if", "then", "than", "so", "because", "while", "when", "where", "how",
    "of", "to", "in", "on", "for", "from", "by", "with", "as", "at", "into",
    "through", "about", "over", "under", "between", "within", "without",
    "during", "after", "before", "against", "via", "per", "also", "not", "no",
    "only", "more", "most", "very", "such", "some", "any", "each", "other",
    "another", "own", "same", "both", "all", "few", "many", "use", "uses",
    "used", "using", "make", "makes", "made", "build", "builds", "built", "create",
    "creates", "created", "based", "base", "learn", "learning", "study", "studying",
    "understand", "understanding", "know", "knowing", "first", "next", "finally", "step",
    "steps", "part", "chapter", "section", "example", "examples", "note", "notes",
    "overview", "introduction", "background", "summary", "conclusion", "references",
    "contents", "resource", "resources", "prerequisite", "prerequisites", "depends",
    "depend", "depending", "rely", "relies", "relied", "requires", "require", "required",
    "needs", "need", "needed", "isn't", "isnt", "doesn't", "doesnt", "can't", "cant",
}


# Single words are accepted only when they are recognisably technical (or
# explicitly capitalised/acronym-like).  This prevents a prose sentence from
# turning every ordinary noun into a node while retaining useful basics.
_HIGH_VALUE_TERMS = {
    # Languages and formats
    "python", "java", "javascript", "typescript", "kotlin", "swift", "rust", "golang",
    "ruby", "php", "scala", "sql", "html", "css", "json", "yaml", "xml", "regex",
    "c", "c++", "c#", "go", "bash", "linux", "git", "docker", "kubernetes",
    # Programming fundamentals
    "variable", "variables", "constant", "constants", "function", "functions", "method",
    "methods", "class", "classes", "object", "objects", "array", "arrays", "list", "lists",
    "dictionary", "dictionaries", "tuple", "tuples", "string", "strings", "boolean", "integer",
    "integers", "loop", "loops", "recursion", "iterator", "iterators", "exception", "exceptions",
    "module", "modules", "package", "packages", "interface", "interfaces", "inheritance",
    "polymorphism", "encapsulation", "abstraction", "complexity", "algorithm", "algorithms",
    "sorting", "searching", "recursion",
    # Data and machine learning
    "data", "dataset", "datasets", "database", "databases", "schema", "schemas", "table", "tables",
    "query", "queries", "index", "indexes", "indexing", "pipeline", "pipelines", "preprocessing",
    "preprocess", "token", "tokens", "tokenization", "embedding", "embeddings", "vector", "vectors",
    "matrix", "matrices", "tensor", "tensors", "feature", "features", "model", "models", "training",
    "train", "trained", "inference", "prediction", "classification", "classifier", "regression",
    "clustering", "cluster", "probability", "statistics", "statistical", "calculus", "algebra", "linear",
    "gradient", "descent", "loss", "optimizer", "optimization", "attention", "transformer", "transformers",
    "neural", "network", "networks", "convolution", "recurrent", "supervised", "unsupervised", "reinforcement",
    "evaluation", "metrics", "accuracy", "precision", "recall", "validation", "regularization", "normalization",
    "segmentation", "generation", "language", "semantic", "retrieval", "search", "ranking", "recommendation",
    "recommendations", "prompt", "prompts", "agent", "agents", "llm", "rag", "bert", "gpt", "qkv", "cnn", "rnn", "mlp", "pca",
    # Transformer/paper vocabulary
    "encoder", "encoders", "decoder", "decoders", "architecture", "sequence", "sequences", "transduction",
    "query", "queries", "key", "keys", "value", "values", "softmax", "relu", "positional", "encoding", "encodings",
    "residual", "dropout", "optimizer", "adam", "bleu", "wmt", "gpu", "gpus", "wordpiece", "wordpieces",
    "autoregressive", "parallelization", "representation", "representations", "operation", "operations", "resolution",
    # Web/application concepts
    "api", "apis", "http", "https", "rest", "graphql", "frontend", "backend", "component", "components",
    "view", "views", "router", "routing", "route", "routes", "request", "requests", "response", "responses",
    "authentication", "authorization", "session", "sessions", "cookie", "cookies", "csrf", "security",
    "permission", "permissions", "user", "users", "account", "accounts", "analytics", "dashboard", "report",
    "reports", "notification", "notifications", "task", "tasks", "worker", "workers", "queue", "queues", "cache",
    "caching", "transaction", "transactions", "migration", "migrations", "service", "services", "gateway", "deployment",
    "testing", "test", "tests", "unit", "integration", "performance", "error", "errors",
    # Knowledge/learning vocabulary
    "knowledge", "concept", "concepts", "graph", "graphs", "node", "nodes", "edge", "edges", "dag", "mastery",
    "assessment", "assessments", "quiz", "quizzes", "question", "questions", "lesson", "lessons", "exercise",
    "exercises", "practice", "progress", "objective", "objectives", "curriculum", "course", "courses", "subject",
    "subjects", "skill", "skills", "evidence",
}


# Common multi-word technical concepts.  They are matched before single words
# so ``machine learning`` is one node instead of two generic nodes.
_KNOWN_PHRASES = {
    "machine learning", "deep learning", "reinforcement learning", "supervised learning", "unsupervised learning",
    "transfer learning", "federated learning", "linear algebra", "abstract algebra", "probability theory",
    "information theory", "graph theory", "calculus", "gradient descent", "stochastic gradient descent",
    "neural network", "convolutional neural network", "recurrent neural network", "natural language processing",
    "natural language understanding", "machine translation", "data preprocessing", "feature engineering",
    "feature extraction", "feature vector", "vector space", "vector database", "graph database", "knowledge graph",
    "attention mechanism", "self-attention", "self attention", "multi-head attention", "multi head attention",
    "transformer architecture", "large language model", "language model", "retrieval augmented generation",
    "retrieval-augmented generation", "prompt engineering", "semantic search", "model training", "model evaluation",
    "model serving", "cross validation", "decision tree", "random forest", "support vector machine",
    "principal component analysis", "dimensionality reduction", "time series", "linear regression", "logistic regression",
    "binary search", "breadth first search", "depth first search", "dynamic programming", "time complexity",
    "space complexity", "data structure", "operating system", "computer network", "object oriented programming",
    "functional programming", "application programming interface", "software engineering", "web development", "data science",
    "computer science", "artificial intelligence", "database schema", "relational database", "data pipeline", "data model",
    "embedding model", "api gateway", "user interface", "user experience", "frontend development", "backend development",
    "unit test", "test driven development", "continuous integration", "version control", "source code", "access control",
    "session management", "error handling", "learning path", "learning objective", "knowledge point", "prerequisite knowledge",
    "prerequisite graph", "scaled dot-product attention", "feed-forward network", "residual connection", "layer normalization",
    "positional encoding", "encoder-decoder attention", "self-attention layer", "attention layer", "beam search",
    "label smoothing", "cross entropy", "long-range dependency", "path length", "sequence transduction model",
}


_TERM_ALIASES = {
    "self attention": "self-attention", "multi head attention": "multi-head attention", "fine tuning": "fine-tuning",
    "retrieval augmented generation": "retrieval-augmented generation", "restful api": "rest api",
    "natural-language processing": "natural language processing",
}


# Chinese terminology is intentionally longest-match-first.  It covers the
# terms most often found in course notes while allowing short unknown heading
# phrases to pass through separately.
_ZH_TERMS = {
    "机器学习", "深度学习", "强化学习", "监督学习", "无监督学习", "迁移学习", "联邦学习", "线性代数", "抽象代数",
    "概率论", "信息论", "图论", "微积分", "统计学", "数据结构", "算法", "面向对象编程", "函数式编程",
    "计算机科学", "软件工程", "操作系统", "计算机网络", "变量", "常量", "函数", "方法", "类", "对象", "数组", "列表",
    "字典", "字符串", "布尔值", "整数", "循环", "递归", "迭代器", "异常处理", "继承", "多态", "封装", "抽象",
    "时间复杂度", "空间复杂度", "排序", "二分查找", "广度优先搜索", "深度优先搜索", "动态规划", "数据库", "关系数据库",
    "数据库模式", "数据表", "查询", "索引", "数据管道", "数据模型", "数据预处理", "特征工程", "特征提取", "特征向量",
    "分词", "标记化", "词元化", "嵌入", "向量", "向量空间", "向量数据库", "矩阵", "张量", "神经网络", "卷积神经网络",
    "循环神经网络", "注意力机制", "自注意力", "多头注意力", "梯度下降", "随机梯度下降", "损失函数", "优化器", "模型训练",
    "模型评估", "模型推理", "分类", "回归", "聚类", "预测", "正则化", "归一化", "决策树", "随机森林", "支持向量机",
    "主成分分析", "降维", "时间序列", "自然语言处理", "自然语言理解", "机器翻译", "知识图谱", "图数据库", "检索增强生成",
    "语义搜索", "提示工程", "大语言模型", "语言模型", "知识点", "知识图", "知识网络", "掌握度", "测评", "评估", "测验",
    "练习", "课程", "学习路径", "学习目标", "前置知识", "前置关系", "学习资源", "证据", "前端", "后端", "组件", "路由",
    "接口", "认证", "授权", "会话", "缓存", "事务", "任务", "队列", "分析", "报告",
}

_ZH_STOP_WORDS = {
    "这是", "这个", "这些", "那些", "我们", "你们", "他们", "以及", "或者", "但是", "如果", "那么", "因为", "所以",
    "通过", "用于", "关于", "其中", "并且", "当前", "内容", "需要", "依赖", "依赖于", "要求", "包括", "包含", "和", "与",
    "及", "是", "的", "在", "对", "将", "被", "由", "先", "再", "然后", "之前", "以后", "基础", "前置", "前提", "掌握",
    "学习", "学会", "使用", "可以", "能够", "相关", "定义", "表示", "称为", "称作", "一个", "一种", "一些", "本章", "本节",
    "示例", "总结", "介绍",
}

_HEADING_STOP_WORDS = {
    "introduction", "overview", "background", "summary", "conclusion", "references", "contents", "example", "examples",
    "exercise", "exercises", "notes", "note", "chapter", "section", "part", "appendix", "introduction and overview",
    "简介", "概述", "背景", "总结", "结论", "参考文献", "目录", "示例", "练习", "笔记", "章节",
}

_ZH_CONNECTOR_RE = re.compile(
    r"需要|依赖于?|要求|包括|包含|以及|和|与|及|是|的|在|对|将|被|由|先|再|然后|之后|之前|基础|前置|前提|掌握|学习|学会|使用|通过|可以|能够|相关|定义|表示|称为|称作"
)


def normalize_term(term: str) -> str:
    """Normalize a display term while retaining technical punctuation."""

    value = unicodedata.normalize("NFKC", str(term or ""))
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = value.replace("`", "")
    value = re.sub(r"^\s*(?:[-*+>]\s+|\d+(?:\.\d+)*[.)、．:-]?\s+)", "", value)
    value = re.sub(r"\s+#+$", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = value.strip(" \t\r\n.,;:!?！？。；，、（）()[]{}<>《》“”‘’\"'")
    value = re.sub(r"\b([A-Za-z][A-Za-z0-9_-]*)['’]s\b", r"\1", value)
    value = value.lower()
    return _TERM_ALIASES.get(value, value)


def _is_chinese(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def _looks_like_heading(value: str) -> bool:
    normalized = normalize_term(value)
    if not normalized or normalized in _HEADING_STOP_WORDS:
        return False
    if _is_chinese(normalized):
        return any(ch not in _ZH_STOP_WORDS for ch in re.findall(r"[\u3400-\u9fff]+", normalized))
    words = normalized.split()
    return bool(words) and any(word not in _STOP_WORDS for word in words)


def _clean_heading(raw: str) -> str:
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", raw)
    value = re.sub(r"[*_`~]", "", value)
    value = re.sub(r"^\s*(?:\d+(?:\.\d+)*[.)、．:-]?\s+|[一二三四五六七八九十百]+[、.．]\s*)", "", value)
    return normalize_term(value)


def _extract_headings(text: str):
    headings = []
    for match in _MD_HEADING.finditer(text):
        name = _clean_heading(match.group(2))
        if _looks_like_heading(name):
            headings.append((len(match.group(1)), name, match.start(), match.end()))
    # Support the common setext form without treating every underlined line as
    # a concept.  It is deliberately limited to a short preceding line.
    lines = text.splitlines(keepends=True)
    offset = 0
    for index in range(len(lines) - 1):
        line = lines[index].strip()
        underline = lines[index + 1].strip()
        if line and re.fullmatch(r"(?:=+|-+)", underline):
            name = _clean_heading(line)
            if _looks_like_heading(name):
                level = 1 if underline.startswith("=") else 2
                start = offset + lines[index].find(line)
                headings.append((level, name, start, offset + len(lines[index]) + len(lines[index + 1])))
        offset += len(lines[index])
    # Numbered section titles are the dominant heading format in academic
    # PDFs (for example ``3 Model Architecture`` and ``3.2 Attention``).
    for match in _NUMBERED_HEADING.finditer(text):
        try:
            section_number = int(match.group("number").split(".", 1)[0])
        except (TypeError, ValueError):
            section_number = 0
        title_text = match.group("title").strip()
        # PDF page numbers followed by captions (``2 Figure 1``) and years
        # at the start of a sentence can look like numbered headings.
        if section_number > 100 or re.match(r"(?:figure|table|input-input)\b", title_text, re.I):
            continue
        name = _clean_heading(match.group("number") + " " + match.group("title"))
        if _looks_like_heading(name):
            level = match.group("number").count(".") + 1
            headings.append((level, name, match.start(), match.end()))
    headings.sort(key=lambda item: item[2])
    return headings


def _phrase_pattern():
    variants = sorted(_KNOWN_PHRASES | set(_TERM_ALIASES), key=len, reverse=True)
    escaped = [re.escape(item).replace(r"\ ", r"\s+") for item in variants]
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(escaped) + r")(?![A-Za-z0-9])", re.I)


_EN_PHRASE = _phrase_pattern()


def _overlaps(start: int, end: int, ranges) -> bool:
    return any(start < right and end > left for left, right in ranges)


def _single_english_candidate(raw: str, normalized: str, force: bool = False) -> bool:
    if not normalized or normalized in _HEADING_STOP_WORDS:
        return False
    if len(normalized) == 1:
        # Single-letter concepts are useful in relation examples (A -> B) and
        # in languages such as C, but should not leak from ordinary prose.
        return bool(force and (raw.isupper() or normalized in {"c", "r", "x"}))
    if normalized in _STOP_WORDS:
        return False
    if normalized in _HIGH_VALUE_TERMS:
        return True
    # Digits and technical punctuation are useful signals, but domains and
    # email fragments from PDF title pages are not concepts.  Keep only
    # sufficiently descriptive identifiers here.
    if re.search(r"\d|[_+#-]", raw):
        return len(normalized) >= 3
    if raw.isupper() and len(normalized) >= 2:
        return True
    return force


def _extract_english(text: str, heading_ranges=(), force: bool = False, strict: bool = False):
    results = []
    phrase_ranges = []
    for match in _EN_PHRASE.finditer(text):
        if _overlaps(match.start(), match.end(), phrase_ranges):
            continue
        name = normalize_term(match.group(0))
        if name and name not in _STOP_WORDS:
            results.append((match.start(), name))
            phrase_ranges.append((match.start(), match.end()))

    covered = list(heading_ranges) + phrase_ranges
    for match in _EN_TOKEN.finditer(text):
        if _overlaps(match.start(), match.end(), covered):
            continue
        raw = match.group(0)
        name = normalize_term(raw)
        if _single_english_candidate(raw, name, force=force) and (not strict or name in _PAPER_SINGLE_TERMS):
            results.append((match.start(), name))
    results.sort(key=lambda item: item[0])
    return results


def _extract_chinese(text: str, force: bool = False):
    results = []
    for span_match in _ZH_SPAN.finditer(text):
        span = span_match.group(0)
        occupied = [False] * len(span)
        matches = []
        # Longest-match-first prevents ``自然语言处理`` from becoming three
        # smaller nodes when it is present in the lexicon.
        for term in sorted(_ZH_TERMS, key=len, reverse=True):
            start = span.find(term)
            while start >= 0:
                end = start + len(term)
                if not any(occupied[start:end]):
                    for pos in range(start, end):
                        occupied[pos] = True
                    matches.append((start, end, term))
                start = span.find(term, start + 1)
        matches.sort(key=lambda item: item[0])
        for start, _end, term in matches:
            results.append((span_match.start() + start, term))

        # Preserve a short unknown phrase, but never the whole long sentence.
        masked = "".join(ch if not occupied[index] else " " for index, ch in enumerate(span))
        for chunk in _ZH_CONNECTOR_RE.split(masked):
            candidate = normalize_term(chunk)
            if not candidate or candidate in _ZH_STOP_WORDS or candidate in _ZH_TERMS:
                continue
            if 2 <= len(candidate) <= 8 and (force or len(span) <= 8):
                results.append((span_match.start() + max(span.find(chunk), 0), candidate))
    results.sort(key=lambda item: item[0])
    return results


def _add_name(names, seen, value, allow_single=False):
    normalized = normalize_term(value)
    if not normalized or normalized in _ZH_STOP_WORDS:
        return None
    if normalized in _STOP_WORDS and not (allow_single and len(normalized) == 1):
        return None
    if normalized not in seen:
        seen.add(normalized)
        names.append(normalized)
    return normalized


def _extract_all_candidates(text: str, heading_ranges=(), force: bool = False, strict: bool = False):
    names, seen = [], set()
    for _position, name in _extract_english(text, heading_ranges, force=force, strict=strict):
        _add_name(names, seen, name)
    for _position, name in _extract_chinese(text, force=force):
        _add_name(names, seen, name)
    return names, seen


def _find_terms_in_fragment(fragment: str, known_names, force: bool = True, strict: bool = False):
    """Resolve one relation endpoint to existing or locally extracted names."""

    fragment = str(fragment or "")
    found = []
    spans = []
    # Match longer names first so ``machine learning`` wins over ``learning``.
    for name in sorted(known_names, key=len, reverse=True):
        if _is_chinese(name):
            starts = [m.start() for m in re.finditer(re.escape(name), fragment, re.I)]
        else:
            starts = [m.start() for m in re.finditer(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])", fragment, re.I)]
        for start in starts:
            end = start + len(name)
            if _overlaps(start, end, spans):
                continue
            spans.append((start, end))
            found.append((start, name))
    found.sort(key=lambda item: item[0])
    if found:
        # A conjunction/list explicitly asks for multiple endpoints.  In a
        # simple noun phrase choose the most specific/last match.
        has_list = bool(re.search(r"\band\b|\bor\b|[,，、;；]|和|与|及|以及", fragment, re.I))
        if not has_list and len(found) > 1:
            found = [max(found, key=lambda item: (len(item[1]), item[0]))]
        return [name for _position, name in found]

    local_names, _ = _extract_all_candidates(fragment, force=force, strict=strict)
    # ``A`` is intentionally excluded from normal prose because it is also an
    # English article. Relation examples can opt into single-letter endpoints,
    # while paper mode ignores formula fragments such as ``O(n)``.
    if not strict:
        for match in _EN_TOKEN.finditer(fragment):
            raw = match.group(0)
            if len(raw) == 1 and raw.isupper():
                name = raw.lower()
                if name not in local_names:
                    local_names.append(name)
    return local_names


# Greedy endpoints backtrack to the relation cue and retain the complete term
# after it.  A lazy ``...?`` here would capture only the first character of a
# target (for example ``Embedding`` -> ``E``).
_ENDPOINT = r"[^,.;!?。！？；;\n]{1,80}"
_RELATION_PATTERNS = [
    # ``A is a prerequisite for B`` / ``A is a prerequisite before B``.
    (re.compile(rf"(?P<source>{_ENDPOINT})\s+(?:is\s+)?(?:an?\s+)?prerequisite\s+(?:for|to|before)\s+(?P<target>{_ENDPOINT})", re.I), "source_target"),
    # A common compressed form in notes: ``A prerequisite B``.
    (re.compile(rf"(?P<source>{_ENDPOINT})\s+prerequisite\s+(?P<target>{_ENDPOINT})", re.I), "source_target"),
    # ``B depends on/requires/needs A`` means A -> B.
    (re.compile(rf"(?P<target>{_ENDPOINT})\s+(?:depends\s+on|relies\s+on|requires|needs|builds\s+on)\s+(?P<source>{_ENDPOINT})", re.I), "target_source"),
    # Academic papers commonly describe architecture with composition and
    # usage language instead of the word ``prerequisite``.
    (re.compile(rf"(?P<target>{_ENDPOINT})\s+(?:is\s+)?(?:based|relying|relies)\s+(?:entirely\s+)?on\s+(?P<source>{_ENDPOINT})", re.I), "target_source"),
    (re.compile(rf"(?P<target>{_ENDPOINT})\s+(?:is\s+)?(?:composed|consists)\s+of\s+(?P<source>{_ENDPOINT})", re.I), "target_source"),
    (re.compile(rf"(?P<target>{_ENDPOINT})\s+uses\s+(?P<source>{_ENDPOINT})", re.I), "target_source"),
    (re.compile(rf"(?P<target>{_ENDPOINT})\s+(?:is\s+)?(?:built|formed|derived)\s+from\s+(?P<source>{_ENDPOINT})", re.I), "target_source"),
    # ``A is the foundation/basis of B`` means A -> B.
    (re.compile(rf"(?P<source>{_ENDPOINT})\s+is\s+(?:the\s+)?(?:foundation|basis|base)\s+of\s+(?P<target>{_ENDPOINT})", re.I), "source_target"),
    # ``A comes before B`` / ``A before B``.
    (re.compile(rf"(?P<source>{_ENDPOINT})\s+(?:comes\s+)?before\s+(?P<target>{_ENDPOINT})", re.I), "source_target"),
    # ``Before B, first learn/master A``.
    (re.compile(rf"before\s+(?P<target>{_ENDPOINT})[,，]\s*(?:first\s+)?(?:learn|master|understand|know)\s+(?P<source>{_ENDPOINT})", re.I), "target_source"),
    # Chinese: ``A 是 B 的前置/基础/前提``.
    (re.compile(rf"(?P<source>[^，。！？；;\n]{{1,32}}?)\s*是\s*(?P<target>[^，。！？；;\n]{{1,32}}?)\s*(?:的)?\s*(?:前置|基础|前提)", re.I), "source_target"),
    # Chinese: ``B 依赖/需要/要求 A``.
    (re.compile(rf"(?P<target>[^，。！？；;\n]{{1,32}}?)\s*(?:依赖于?|需要|要求|基于)\s*(?P<source>[^，。！？；;\n]{{1,32}})", re.I), "target_source"),
    # Chinese: ``先学 A 再学 B``.
    (re.compile(rf"先\s*(?:学习|学|掌握)\s*(?P<source>[^，。！？；;\n]{{1,24}}?)\s*(?:再|然后)\s*(?:学习|学|掌握)\s*(?P<target>[^，。！？；;\n]{{1,24}})", re.I), "source_target"),
    # Chinese: ``学习 B 前先掌握 A``.
    (re.compile(rf"(?:学习|学|掌握)\s*(?P<target>[^，。！？；;\n]{{1,24}}?)\s*(?:之前|前)\s*(?:先)?\s*(?:学习|学|掌握)\s*(?P<source>[^，。！？；;\n]{{1,24}})", re.I), "target_source"),
    # Chinese: ``A 在 B 之前``.
    (re.compile(rf"(?P<source>[^，。！？；;\n]{{1,24}}?)\s*在\s*(?P<target>[^，。！？；;\n]{{1,24}}?)\s*之前", re.I), "source_target"),
]


def _split_segments(text: str):
    return [segment for segment in re.split(r"(?:\r?\n+|(?<=[。！？!?；;\.])\s+)", text) if segment.strip()]


def _extract_relations(text: str, known_names, heading_edges=(), strict: bool = False):
    # Section hierarchy is structural containment, not a learning
    # prerequisite.  Keep this extractor focused on explicit prerequisite
    # language; the caller adds inferred ``contains`` edges separately.
    edges = []
    edge_set = {(source, target) for source, target in edges}
    names = list(known_names)
    known_set = set(names)

    for segment in _split_segments(text):
        for pattern, orientation in _RELATION_PATTERNS:
            for match in pattern.finditer(segment):
                left = _find_terms_in_fragment(match.group("source"), known_set, force=True, strict=strict)
                right = _find_terms_in_fragment(match.group("target"), known_set, force=True, strict=strict)
                if orientation == "target_source":
                    # These patterns name the dependent first (``B depends
                    # on A``).  The regex stores A in ``source`` and B in
                    # ``target``, so the captures already have A -> B order.
                    source_terms, target_terms = left, right
                else:
                    source_terms, target_terms = left, right
                # Relation endpoints may be generic identifiers (A/B) that
                # normal prose filtering intentionally skipped.  Add them to
                # the node set before recording the edge.
                for term in source_terms + target_terms:
                    _add_name(names, known_set, term, allow_single=True)
                for source in source_terms:
                    source = normalize_term(source)
                    for target in target_terms:
                        target = normalize_term(target)
                        if source and target and source != target and (source, target) not in edge_set:
                            edge_set.add((source, target))
                            edges.append((source, target))
    return names, edges


def _heading_edges(headings):
    edges = []
    stack = []
    for level, name, _start, _end in headings:
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            parent = stack[-1][1]
            if parent != name:
                edges.append((parent, name))
        stack.append((level, name))
    return edges


def _attach_orphan_concepts(text: str, names, edges, headings):
    """Attach extracted body terms to the section that introduces them.

    Academic PDFs rarely say ``A is a prerequisite for B`` explicitly.  The
    section hierarchy is the reliable structure we do have, so an otherwise
    disconnected term becomes a child of the deepest section where it occurs.
    Structural and cross-component links are marked as inferred by the caller.
    """

    inferred_relations = {}

    if not headings:
        # With no document structure, retain the extracted terms but connect
        # them in first-occurrence order as weak associations.  This keeps a
        # graph navigable without pretending that the extractor proved a
        # prerequisite relation.
        ordered_names = list(dict.fromkeys(names))
        for source, target in zip(ordered_names, ordered_names[1:]):
            pair = (source, target)
            if pair not in edges:
                edges.append(pair)
                inferred_relations[pair] = "related"
        return edges, inferred_relations

    # Keep section hierarchy in the graph for navigation, but do not let it
    # masquerade as a prerequisite relation.  The extraction boundary adds
    # the relation metadata after this function returns.
    edge_set = set(edges)
    for pair in _heading_edges(headings):
        if pair not in edge_set:
            edges.append(pair)
            edge_set.add(pair)
            inferred_relations[pair] = "contains"

    heading_names = {name for _level, name, _start, _end in headings}
    degree = {name: 0 for name in names}
    for source, target in edges:
        degree[source] = degree.get(source, 0) + 1
        degree[target] = degree.get(target, 0) + 1

    sections = []
    for index, (level, heading, start, _end) in enumerate(headings):
        section_end = len(text)
        for next_level, _next_heading, next_start, _next_end in headings[index + 1 :]:
            if next_level <= level:
                section_end = next_start
                break
        sections.append((level, heading, start, section_end))

    def occurrences(name):
        if _is_chinese(name):
            pattern = re.compile(re.escape(name), re.I)
        else:
            pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])", re.I)
        return [match.start() for match in pattern.finditer(text)]

    def introduces_cycle(source, target):
        adjacency = {}
        for left, right in edges:
            adjacency.setdefault(left, []).append(right)
        pending, seen = [target], set()
        while pending:
            current = pending.pop()
            if current == source:
                return True
            if current in seen:
                continue
            seen.add(current)
            pending.extend(adjacency.get(current, ()))
        return False

    for name in names:
        if degree.get(name, 0) or name in heading_names:
            continue
        positions = occurrences(name)
        candidates = [
            (level, start, heading)
            for level, heading, start, end in sections
            if any(start <= position < end for position in positions)
        ]
        if candidates:
            # Prefer the most specific section, then the earliest occurrence.
            _level, _start, parent = max(candidates, key=lambda item: (item[0], -item[1]))
        elif positions:
            prior = [item for item in sections if item[2] <= positions[0]]
            parent = max(prior, key=lambda item: item[2])[1] if prior else sections[0][1]
        else:
            parent = sections[0][1]
        if parent != name:
            pair = (parent, name)
            if pair in edge_set:
                continue
            edges.append(pair)
            edge_set.add(pair)
            inferred_relations[pair] = "contains"
            degree[parent] = degree.get(parent, 0) + 1
            degree[name] = degree.get(name, 0) + 1

    # Keep separate top-level paper sections in reading order so the result is
    # one navigable DAG instead of several unrelated trees.
    top_level = [name for level, name, _start, _end in headings if level == 1]
    for source, target in zip(top_level, top_level[1:]):
        if (source, target) not in edge_set and not introduces_cycle(source, target):
            edges.append((source, target))
            edge_set.add((source, target))
            inferred_relations[(source, target)] = "contains"

    # A relation can connect two nodes while still leaving the component
    # detached from the paper's section tree (for example abstract terms such
    # as ``recurrent`` and ``transduction``). Attach each remaining weak
    # component to the nearest section as a non-prerequisite association.
    adjacency = {name: set() for name in names}
    for source, target in edges:
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)

    components = []
    unseen = set(adjacency)
    while unseen:
        root = next(iter(unseen))
        stack = [root]
        component = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            unseen.discard(current)
            stack.extend(adjacency.get(current, ()))
        components.append(component)

    def first_position(name):
        positions = occurrences(name)
        return min(positions) if positions else len(text)

    heading_component = next(
        (component for component in components if component.intersection(heading_names)),
        None,
    )
    anchor = heading_component or min(components, key=lambda component: min(first_position(name) for name in component))
    for component in sorted(
        (item for item in components if item is not anchor),
        key=lambda item: min(first_position(name) for name in item),
    ):
        candidate = min(component, key=first_position)
        positions = occurrences(candidate)
        parent = None
        if positions:
            first = min(positions)
            matching_sections = [
                (level, start, heading)
                for level, heading, start, end in sections
                if start <= first < end
            ]
            if matching_sections:
                _level, _start, parent = max(matching_sections, key=lambda item: (item[0], -item[1]))
        parent = parent or headings[0][1]
        if parent in component:
            parent = min(anchor, key=first_position)
        pair = (parent, candidate)
        if pair not in edge_set and not introduces_cycle(parent, candidate):
            edges.append(pair)
            edge_set.add(pair)
            inferred_relations[pair] = "related"
        anchor.update(component)

    return edges, inferred_relations


def _prepare_extraction_text(text: str) -> str:
    """Remove predictable paper front/back matter before concept extraction."""

    source = str(text or "")
    paper_like = bool(re.search(r"\b(?:abstract|arxiv|doi|nips|neurips|wmt)\b", source, re.I))
    lines = []
    for line in source.splitlines():
        stripped = line.strip()
        if paper_like and stripped.casefold() == "references":
            break
        if re.fullmatch(r"\d{1,3}", stripped):
            continue
        if re.match(r"^(?:provided proper attribution|arxiv:\s*|copyright\s+)", stripped, re.I):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    # Author addresses and domains are frequent PDF title-page noise.  Keep
    # normal prose punctuation untouched for Markdown/TXT inputs.
    cleaned = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", " ", cleaned, flags=re.I)
    return cleaned


def extract_knowledge(text: str) -> dict:
    """Extract conservative concept nodes and prerequisite edges offline."""

    source = _prepare_extraction_text(unicodedata.normalize("NFKC", str(text or "")))
    paper_like = bool(re.search(r"\b(?:abstract|arxiv|doi|nips|neurips|wmt)\b", source, re.I))
    headings = _extract_headings(source)
    heading_ranges = [(start, end) for _level, _name, start, end in headings]
    names, _seen = _extract_all_candidates(source, heading_ranges=heading_ranges, strict=paper_like)

    # Headings are high-confidence concepts and should appear first in the
    # payload, followed by terms found in the body.
    ordered = []
    ordered_seen = set()
    for _level, name, _start, _end in headings:
        _add_name(ordered, ordered_seen, name)
    for name in names:
        _add_name(ordered, ordered_seen, name)

    heading_edges = _heading_edges(headings)
    ordered, relation_edges = _extract_relations(source, ordered, heading_edges=heading_edges, strict=paper_like)
    explicit_edges = set(relation_edges)
    relation_edges, inferred_relations = _attach_orphan_concepts(source, ordered, relation_edges, headings)

    nodes = [{"id": name.replace(" ", "-"), "name": name, "type": "concept"} for name in ordered]
    edges = [
        {
            "from": source_name,
            "to": target_name,
            "relation": "prerequisite" if (source_name, target_name) in explicit_edges else inferred_relations.get((source_name, target_name), "contains"),
            "inferred": (source_name, target_name) not in explicit_edges,
        }
        for source_name, target_name in relation_edges
        if source_name != target_name
    ]
    return {"nodes": nodes, "edges": edges}


def deduplicate(nodes: list[dict]) -> list[dict]:
    """De-duplicate nodes by normalized display name, preserving metadata."""

    out, seen = [], set()
    for raw in nodes or []:
        item = dict(raw) if isinstance(raw, dict) else {"name": raw}
        name = normalize_term(item.get("name", item.get("id", "")))
        if not name or name in seen:
            continue
        seen.add(name)
        item["id"] = item.get("id") or name.replace(" ", "-")
        item["name"] = name
        out.append(item)
    return out
