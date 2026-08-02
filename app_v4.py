"""
アパレル商品説明文ジェネレーター（Streamlit本体）
apparel_copy_v4.py と同じフォルダに置き、次で起動:
    streamlit run app.py
前提: 環境変数 ANTHROPIC_API_KEY を設定済み。
"""

import os
import streamlit as st
from apparel_copy_v4 import generate_copy, extract_known_facts, _as_list

st.set_page_config(page_title="アパレル商品説明文ジェネレーター", layout="wide")

# ── サイドバー（設定） ──────────────────────────────
with st.sidebar:
    st.header("設定")
    if os.environ.get("ANTHROPIC_API_KEY"):
        st.success("API キーを環境変数から読み込みました")
    else:
        st.error("環境変数 ANTHROPIC_API_KEY が未設定です")

    st.subheader("仕入れ元ページから抽出（任意）")
    source_text = st.text_area(
        "仕入れ元ページのテキスト（英語など）",
        height=100,
        help="商品ページの本文をそのままコピー&ペーストしてください。"
             "素材・サイズ・価格などの事実項目だけを日本語に抽出し、下の補足情報欄に入れます。"
             "宣伝文句やキャッチコピーは取り込みません。",
    )
    if st.button("補足情報を抽出"):
        if not source_text.strip():
            st.warning("仕入れ元ページのテキストを貼り付けてください。")
        else:
            try:
                with st.spinner("抽出中..."):
                    extracted = extract_known_facts(source_text)
            except Exception as e:
                st.error(f"抽出に失敗しました: {e}")
            else:
                st.session_state["known_facts_draft"] = extracted.get("known_facts_ja", "")
                nf = extracted.get("not_found") or []
                if nf:
                    st.info("ページに記載が見当たらなかった項目： " + " / ".join(nf))

    known = st.text_area(
        "補足情報（任意）",
        height=120,
        value=st.session_state.get("known_facts_draft", ""),
        help="画像で見えない確定情報だけを入れてください（素材混率・サイズ・価格など）。"
             "袖や襟など画像で分かる項目は書かなくて構いません。"
             "例）素材: ポリエステル80%・麻20% / サイズ: F / 定価: 6900円",
    )
    gender = st.radio("ターゲット", ["auto", "mens", "ladies"], horizontal=True)
    revise = st.checkbox("自己添削を行う", value=True,
                         help="説明文を文体ルールで一度書き直します（API呼び出しが1回増えます）。")

# ── 本体 ───────────────────────────────────────────
st.title("アパレル商品説明文ジェネレーター")
st.caption("商品画像から EC 用のテキストを自動生成します（メンズ・レディース両対応）")

ups = st.file_uploader(
    "商品画像をアップロード（複数可）",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
)

if st.button("生成する", type="primary"):
    if not ups:
        st.warning("商品画像をアップロードしてください。")
    else:
        try:
            with st.spinner("生成中..."):
                res = generate_copy(
                    [u.getvalue() for u in ups],
                    gender=gender,
                    known_facts=known,
                    revise=revise,
                )
        except Exception as e:
            st.error(f"生成に失敗しました: {e}")
        else:
            col_img, col_txt = st.columns([1, 1.4])
            with col_img:
                for u in ups:
                    st.image(u, use_container_width=True)
            with col_txt:
                st.subheader(res["product_name"])
                st.write(res["description"])
                st.markdown("**カテゴリ**： " + (res.get("category") or "―"))
                tags = _as_list(res.get("tags"))
                if tags:
                    st.markdown("**タグ**： " + " / ".join(tags))

                conflicts = _as_list(res.get("conflicts"))
                if conflicts:
                    st.warning("補足情報と画像の食い違い：\n\n- " + "\n- ".join(conflicts))
                uncertain = _as_list(res.get("uncertain"))
                if uncertain:
                    st.info("画像から断定できず保留した項目：\n\n- " + "\n- ".join(uncertain))

                with st.expander("画像から読み取った事実（visible_facts）"):
                    st.write(res.get("visible_facts", ""))