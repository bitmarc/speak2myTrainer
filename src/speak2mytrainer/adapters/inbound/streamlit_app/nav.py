"""Referencias a las páginas, para enlazarlas entre sí (`st.page_link`, `st.switch_page`)."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


@dataclass
class Nav:
    practices: st.Page | None = None
    new_practice: st.Page | None = None
    practice: st.Page | None = None

    def go(self, page: st.Page | None, **query: str) -> None:
        assert page is not None
        st.switch_page(page, query_params=query or None)
