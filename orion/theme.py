# SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Thème du panneau et de ses fenêtres, partagé par tous ses onglets."""
from tkinter import ttk

# Thème futuriste épuré : noir bleuté, accents cyan, aucune image (léger)
FOND, SURFACE, TEXTE, ACCENT, DISCRET = "#05090d", "#0c141b", "#cfe9f2", "#29e0ff", "#5b7683"


def theme(root):
    root.configure(bg=FOND)
    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure(".", background=FOND, foreground=TEXTE, fieldbackground=SURFACE, bordercolor="#14313d",
                 lightcolor=FOND, darkcolor=FOND, font=("Segoe UI", 10))
    st.configure("TNotebook", background=FOND, borderwidth=0)
    st.configure("TNotebook.Tab", background=FOND, foreground=DISCRET, padding=(14, 6), borderwidth=0)
    st.map("TNotebook.Tab", background=[("selected", SURFACE)], foreground=[("selected", ACCENT)])
    st.configure("TButton", background=SURFACE, foreground=ACCENT, borderwidth=1, focusthickness=0,
                 padding=(10, 4))
    st.map("TButton", background=[("active", "#123040")])
    st.configure("TLabelframe", background=FOND, bordercolor="#14313d")
    st.configure("TLabelframe.Label", background=FOND, foreground=ACCENT)
    st.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXTE, rowheight=24)
    st.configure("Treeview.Heading", background=FOND, foreground=ACCENT)
    st.map("Treeview", background=[("selected", "#123040")])
    st.configure("TCheckbutton", background=FOND, foreground=TEXTE)
    st.configure("TRadiobutton", background=FOND, foreground=TEXTE)
    st.configure("TEntry", foreground=TEXTE, insertcolor=ACCENT)
    root.option_add("*Listbox.background", SURFACE)
    root.option_add("*Listbox.foreground", TEXTE)
    root.option_add("*Listbox.selectBackground", "#123040")
    root.option_add("*Listbox.borderWidth", 0)
