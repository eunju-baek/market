"""Google 뉴스 RSS에서 미국 증시·경제·반도체 기사 제목을 모아 GitHub Models(무료)로 한글 요약하고 summary.json을 만든다."""
import json
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

import urllib.request

import feedparser

QUERIES = {
    "market": "stock market Wall Street S&P 500 Nasdaq",
    "macro": "Federal Reserve inflation jobs US economy",
    "semis": "semiconductor stocks Nvidia chip",
}
PER_FEED = 12      # 카테고리별로 모델에 보여줄 후보 기사 수
PICK = 5           # 카테고리별로 남길 기사 수
# 앞에서부터 시도하고, 쓸 수 없는 모델이면 다음 모델로 넘어간다
MODELS = ["openai/gpt-4.1-mini", "openai/gpt-4o-mini", "meta/Llama-3.3-70B-Instruct"]
ENDPOINT = "https://models.github.ai/inference/chat/completions"


def fetch(query):
    url = ("https://news.google.com/rss/search?q=" + quote_plus(query + " when:1d")
           + "&hl=en-US&gl=US&ceid=US:en")
    out = []
    for e in feedparser.parse(url).entries[:PER_FEED]:
        source = e.get("source", {}).get("title", "")
        title = e.get("title", "")
        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)]
        out.append({"title": title, "source": source, "url": e.get("link", "")})
    return out


def ask(prompt):
    token = os.environ["GITHUB_TOKEN"]
    last_err = None
    for model in MODELS:
        body = json.dumps({"model": model, "max_tokens": 2000,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(ENDPOINT, data=body, headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            print("사용 모델:", model)
            return data["choices"][0]["message"]["content"]
        except Exception as e:  # 모델 없음, 한도 초과 등
            print(f"{model} 실패: {e}")
            last_err = e
    raise SystemExit(f"모든 모델 호출 실패: {last_err}")


def main():
    articles = {k: fetch(q) for k, q in QUERIES.items()}
    lines = []
    for cat, items in articles.items():
        for i, a in enumerate(items):
            lines.append(f"{cat}:{i} | {a['source']} | {a['title']}")
    if not lines:
        raise SystemExit("RSS에서 기사를 가져오지 못했습니다.")

    prompt = (
        "아래는 최근 24시간 미국 경제 뉴스 기사 제목 목록이다. 각 줄은 'id | 언론사 | 제목' 형식이다.\n\n"
        + "\n".join(lines)
        + f"\n\n카테고리(market, macro, semis)마다 중요한 기사를 최대 {PICK}개 골라 한국어로 한 문장씩 요약하라. "
        "중복된 소식은 하나만 고른다. 제목에 없는 사실, 수치, 해석은 추가하지 않는다. "
        "outlook에는 위 제목들에서 드러난 앞으로 주목할 점을 한국어 문장 최대 3개로 쓴다. 근거가 부족하면 빈 배열로 둔다. "
        "반드시 아래 형식의 JSON만 출력하라.\n"
        '{"market":[{"id":"market:0","ko":"..."}],"macro":[...],"semis":[...],"outlook":["..."]}'
    )
    text = ask(prompt)
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    picked = json.loads(text)

    kst = timezone(timedelta(hours=9))
    result = {"updated": datetime.now(kst).strftime("%Y-%m-%d %H:%M KST")}
    for cat in QUERIES:
        rows = []
        for p in picked.get(cat, []):
            c, _, idx = str(p.get("id", "")).partition(":")
            if c != cat or not idx.isdigit() or int(idx) >= len(articles[cat]):
                continue  # 목록에 없는 id는 버린다 (링크를 지어내지 않도록)
            a = articles[cat][int(idx)]
            rows.append({"ko": p.get("ko", ""), **a})
        result[cat] = rows
    result["outlook"] = [s for s in picked.get("outlook", []) if isinstance(s, str)][:3]

    with open("summary.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("summary.json 저장:", {k: len(v) for k, v in result.items() if isinstance(v, list)})


if __name__ == "__main__":
    main()
