"""
アパレルEC 商品コピー生成 v4（補足情報の矛盾に強い版）
v3からの変更点:
  - known_facts の扱いを2分:
      * 画像で判断できない属性(素材混率/サイズ/価格/ケア/ブランド/生産国)
        → known_facts を確定情報として採用
      * 画像で判断できる属性(色/袖丈/襟型/全体丈/柄の有無/シルエット)
        → 画像を優先。known_facts と食い違えば画像を採用し conflicts に記録
  - known_facts 内の矛盾(例: 素材が2種類書かれている)も conflicts に入れ断定回避
  - 出力に conflicts フィールドを追加
その他(文体B / FEW_SHOT / 複数画像 / リサイズ / 自己添削 / ツールでJSON強制)はv3を継承。
※ 未実行。そちらで動かして調整してください。
"""

import io
import re
import base64
import anthropic
from PIL import Image

MODEL = "claude-sonnet-5"
MAX_EDGE = 1568
TEMP_GEN = 0.5
TEMP_REVISE = 0.6

CATEGORIES = [
    "トップス > Tシャツ・カットソー", "トップス > シャツ・ブラウス",
    "トップス > ニット・セーター", "トップス > スウェット・パーカー",
    "アウター > ジャケット", "アウター > ブルゾン・デニムジャケット",
    "アウター > コート", "ボトムス > パンツ", "ボトムス > デニム",
    "ボトムス > スカート", "ワンピース", "セットアップ", "その他",
]

STYLE_RULES = """\
- です・ます調。読み手に語りかける親しみやすいトーン。
- 2〜4文。一文は長くしすぎない（およそ60字まで）。
- 情報の順序: (1)全体の魅力を一言 →(2)素材・肌触り・作り →(3)サイズ感/シルエット →(4)コーデ提案 →(5)サイズ展開など補足。
- 具体名詞で書く（素材名・編み/織り・襟や裾などのディテール名）。曖昧な形容の連発は避ける。
- 禁止: 「まさに」「究極」「〜な一着」の多用、根拠のない断定、感嘆符の多用。
- 日本語だけで書く。英単語をそのまま混ぜない（"covering" のような表記は不可。必ず日本語に言い換える）。
- 専門用語は最小限。使う場合は平易に言い換える（例: ドロップ肩ヨーク→ゆったりした肩、キャップスリーブ→短い袖）。
- 文は4つまで。1文が長くなったら分ける。仕様の羅列にせず、読んで情景が浮かぶ文にする。
- known_facts と visible_facts の範囲を超える断定はしない（素材混率・サイズは確定情報のみ）。"""

# known_facts と画像の優先順位ルール（誤入力に強くするための肝）
RECONCILE_RULES = """\
補足情報(known_facts)と画像の突き合わせ:
- 画像で見える属性(色/袖丈/襟型/全体の丈/柄の有無/シルエット)は画像を正とする。
  known_facts がこれと食い違う場合は画像を採用し、その食い違いを conflicts に記録する。
  （例: known_facts に「ノースリーブ」とあるが画像は半袖 → 半袖を採用し conflicts に記載）
- 画像で判断できない属性(素材混率/サイズ/価格/ケア/ブランド/生産国)のみ known_facts を確定情報として採用する。
- known_facts の中に矛盾する記述がある場合(例: 素材が2通り書かれている)は、
  どちらも断定せず uncertain に入れ、conflicts に矛盾点を記録する。
- ファーの種類: known_facts に「フォーファー」「フェイクファー」「エコファー」または
  人工毛の素材(アクリル/モダクリル/ポリエステル等)の記載があれば、そのファーは人工毛(フェイクファー)と確定する。
  本文には「フェイクファー（エコファー）」等と明記し、「本毛か人工毛か」を uncertain に入れない。
  リアルファー(本毛)と確定できるのは known_facts に明記がある場合のみ。"""

FEW_SHOT = [
    {
        "facts": "ベージュのテーパードチノパンツ / コットン98%・ポリウレタン2% / サイズS〜XL",
        "ideal": (
            "きれいめにもカジュアルにも使える、ベージュのテーパードチノパンツです。"
            "コットン混のほどよい厚みで一年を通して穿きやすく、少しストレッチが効くので動きやすさも快適。"
            "裾に向かって細くなるシルエットが脚をすっきり見せてくれます。"
            "シャツを合わせて通勤に、スニーカーで休日にと出番の多い一本。S〜XLの4サイズ展開です。"
        ),
    },
    {
        "facts": "深いグリーンのAラインワンピース / レーヨン混 / 七分袖 / フリーサイズ",
        "ideal": (
            "一枚で着こなしが決まる、深いグリーンのAラインワンピースです。"
            "とろみのある生地が上品に揺れて、体型を拾いにくいのもうれしいところ。"
            "七分袖で二の腕をさりげなくカバーできます。"
            "フラットシューズで普段使いに、パンプスを合わせればきれいめの場にも。フリーサイズです。"
        ),
    },
    {
        "facts": "グレーのマキシワンピース / ラウンドネック・短い袖・背中リボン / ポリエステルに麻を合わせた薄手 / 大人カジュアル",
        "ideal": (
            "肩の力を抜いて着られる、グレーのゆったりマキシワンピースです。"
            "ポリエステルに麻を合わせた薄手で軽やかな生地が、さらりと心地よく揺れます。"
            "ラウンドネックに、背中のリボンがさりげないアクセント。"
            "かごバッグとサンダルを合わせれば、抜け感のある大人カジュアルに仕上がります。"
        ),
    },
]

SUBMIT_TOOL = {
    "name": "submit_product_copy",
    "description": "生成した商品コピーを構造化して提出する。",
    "input_schema": {
        "type": "object",
        "properties": {
            "visible_facts": {"type": "string", "description": "画像から確実に読み取れる事実のみ。最初に埋める。"},
            "product_name": {"type": "string", "description": "30文字程度まで。ブランド名は確証がある場合のみ。"},
            "description": {"type": "string", "description": "文体Bの説明文。120〜250字程度。"},
            "category": {"type": "string", "enum": CATEGORIES},
            "tags": {"type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 10},
            "uncertain": {"type": "array", "items": {"type": "string"}, "description": "推測を避けた項目。"},
            "conflicts": {
                "type": "array", "items": {"type": "string"},
                "description": "補足情報と画像が食い違った点、または補足情報内の矛盾。無ければ空配列。",
            },
        },
        "required": ["visible_facts", "product_name", "description", "category", "tags", "uncertain", "conflicts"],
    },
}


def _as_list(x) -> list:
    """配列はそのまま、文字列は区切り文字で分割して返す。文字列を1文字ずつにしない。"""
    if isinstance(x, list):
        return [str(i).strip() for i in x if str(i).strip()]
    if isinstance(x, str) and x.strip():
        parts = re.split(r"[、,／/・|\n]+", x.strip())
        return [p.strip() for p in parts if p.strip()]
    return []


def _prep_image(image_bytes: bytes) -> str:
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = im.size
    scale = min(1.0, MAX_EDGE / max(w, h))
    if scale < 1.0:
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


def _render_fewshot() -> str:
    return "\n\n".join(f"[情報] {ex['facts']}\n[理想の説明文] {ex['ideal']}" for ex in FEW_SHOT)


def build_system_prompt(gender: str, brand_notes: str) -> str:
    gmap = {"mens": "メンズ", "ladies": "レディース", "auto": "画像から推定（不明なら中性的）"}
    lines = [
        "あなたはアパレルECの商品コピーライター兼、画像の観察者です。",
        "手順: (1) visible_facts に画像から確実に読める事実だけを列挙 →(2) 下記ルールで known_facts と突き合わせ →(3) その範囲でのみ各項目を作成。",
        "\n【補足情報と画像の優先順位（厳守）】\n" + RECONCILE_RULES,
        "\n画像でも補足情報でも確定できない素材混率・サイズ・ケア・型番・ブランドは断定せず uncertain に入れる。",
        f"\nターゲット: {gmap.get(gender, gmap['auto'])}",
        "\n【説明文の文体ルール（厳守）】\n" + STYLE_RULES,
        "\n【お手本】この語り口・構成・長さに合わせる:\n" + _render_fewshot(),
        "\n必ず submit_product_copy ツールを1回呼び出して返すこと。",
    ]
    if brand_notes.strip():
        lines.append(f"店舗/ブランド補足: {brand_notes.strip()}")
    return "\n".join(lines)


def _revise_description(client, draft: str, facts_context: str) -> str:
    msg = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=(
            "次の商品説明文を、文体ルールに沿って自然に書き直してください。"
            "与えられた事実の範囲を超える新情報は足さないこと。"
            "出力は書き直した説明文のみ（前置き・記号なし）。\n\n【文体ルール】\n" + STYLE_RULES
        ),
        messages=[{"role": "user", "content": f"【この事実の範囲内で】\n{facts_context}\n\n【元の説明文】\n{draft}"}],
    )
    out = "".join(b.text for b in msg.content if b.type == "text").strip()
    return out or draft


def generate_copy(
    images: list[bytes],
    gender: str = "auto",
    brand_notes: str = "",
    known_facts: str = "",
    revise: bool = True,
) -> dict:
    client = anthropic.Anthropic()

    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _prep_image(b)}}
        for b in images
    ]
    user_text = "この商品のEC掲載用テキストを作成してください。"
    if known_facts.strip():
        user_text += f"\n\n【補足情報 known_facts（画像と食い違う点は画像優先。優先順位ルールに従う）】\n{known_facts.strip()}"
    content.append({"type": "text", "text": user_text})

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1300,
        system=build_system_prompt(gender, brand_notes),
        tools=[SUBMIT_TOOL],
        tool_choice={"type": "tool", "name": "submit_product_copy"},
        messages=[{"role": "user", "content": content}],
    )

    result = None
    for block in resp.content:
        if block.type == "tool_use" and block.name == "submit_product_copy":
            result = dict(block.input)
            break
    if result is None:
        raise RuntimeError("ツール出力が取得できませんでした: " + str(resp.content))

    if revise:
        facts_ctx = "visible_facts: " + result.get("visible_facts", "")
        if known_facts.strip():
            facts_ctx += "\nknown_facts: " + known_facts.strip()
        result["description"] = _revise_description(client, result["description"], facts_ctx)

    # 配列であるべき項目を正規化（文字列で返っても1文字ずつにならないようにする）
    for key in ("tags", "uncertain", "conflicts"):
        result[key] = _as_list(result.get(key))
    if not str(result.get("category") or "").strip():
        result["category"] = "その他"

    return result


# ── 仕入れ元ページ(英語等)から known_facts を抽出 ──────────────
EXTRACT_TOOL = {
    "name": "submit_known_facts",
    "description": "仕入れ元ページのテキストから事実項目のみを抽出して提出する。",
    "input_schema": {
        "type": "object",
        "properties": {
            "known_facts_ja": {
                "type": "string",
                "description": (
                    "抽出できた事実項目を日本語で1行1項目にまとめたテキスト。"
                    "例: 素材: コットン100% / サイズ: S,M,L / 定価: $120 / 生産国: イタリア。"
                    "宣伝文句・煽り表現・ブランドの謳い文句は含めない。確認できない項目は書かない。"
                ),
            },
            "not_found": {
                "type": "array", "items": {"type": "string"},
                "description": "ページ内に記載が見当たらなかった一般的な項目（例: サイズ表, ケア方法）。",
            },
        },
        "required": ["known_facts_ja", "not_found"],
    },
}


def extract_known_facts(source_text: str) -> dict:
    """
    仕入れ元ページ(英語等)のコピー&ペーストしたテキストから、
    素材/サイズ/価格/ケア/生産国など事実項目のみを日本語に翻訳・抽出する。
    宣伝文句やブランドの謳い文句は取り込まない。
    戻り値: {"known_facts_ja": str, "not_found": list[str]}
    生成した known_facts_ja はそのまま generate_copy(known_facts=...) に渡せる。
    """
    if not source_text.strip():
        return {"known_facts_ja": "", "not_found": []}

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=800,
        system=(
            "あなたは海外アパレルECページから事実情報だけを抽出する担当者です。"
            "入力は仕入れ元ページ(英語等)からコピーされたテキストです。"
            "素材混率・サイズ展開・価格・ケア方法・生産国・型番など、客観的な事実項目のみを日本語に翻訳して抽出してください。"
            "『シーズンを代表する』『上質な』のような宣伝文句・ブランドの謳い文句・キャッチコピーは一切含めないでください。"
            "ページに記載が無い項目は書かないでください（推測で埋めない）。"
            "必ず submit_known_facts ツールを1回呼び出して結果を返してください。"
        ),
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "submit_known_facts"},
        messages=[{"role": "user", "content": f"【仕入れ元ページのテキスト】\n{source_text.strip()}"}],
    )

    for block in resp.content:
        if block.type == "tool_use" and block.name == "submit_known_facts":
            out = dict(block.input)
            out["not_found"] = _as_list(out.get("not_found"))
            return out
    raise RuntimeError("ツール出力が取得できませんでした: " + str(resp.content))


# ── Streamlit組み込み例 ─────────────────────────────────────
# from apparel_copy_v4 import generate_copy, extract_known_facts
# ups = st.file_uploader("商品画像（複数可）", type=["jpg","jpeg","png"], accept_multiple_files=True)
# gender = st.radio("ターゲット", ["auto","mens","ladies"], horizontal=True)
#
# src_text = st.text_area("仕入れ元ページのテキスト（英語など・任意）",
#                         help="商品ページの本文をそのままコピー&ペースト。素材/サイズ/価格等を自動で日本語抽出します。")
# if src_text and st.button("補足情報を抽出"):
#     extracted = extract_known_facts(src_text)
#     st.session_state["known_facts_draft"] = extracted["known_facts_ja"]
#     if extracted["not_found"]:
#         st.info("ページに記載が見当たらなかった項目: " + " / ".join(extracted["not_found"]))
#
# known = st.text_area("補足情報（素材/サイズ/価格など・任意）",
#                      value=st.session_state.get("known_facts_draft", ""))
# revise = st.checkbox("自己添削を行う", value=True)
# if ups and st.button("生成する"):
#     res = generate_copy([u.getvalue() for u in ups], gender=gender, known_facts=known, revise=revise)
#     st.subheader(res["product_name"]); st.write(res["description"])
#     st.caption("カテゴリ: " + res["category"]); st.write("タグ: " + " / ".join(res["tags"]))
#     if res.get("conflicts"):
#         st.warning("補足情報と画像の食い違い: " + " / ".join(res["conflicts"]))
#     if res.get("uncertain"):
#         st.info("画像から断定できず保留: " + " / ".join(res["uncertain"]))