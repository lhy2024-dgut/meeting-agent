# -*- coding: utf-8 -*-
"""联系人管理页 — 联系人 CRUD + 群组管理"""

import re

import streamlit as st

from db.repository import ContactRepository


def page_contacts():
    st.header("联系人管理")

    db = ContactRepository()

    tab_contacts, tab_groups = st.tabs(["👤 联系人", "👥 群组"])

    with tab_contacts:
        _contacts_tab(db)

    with tab_groups:
        _groups_tab(db)


# ─────────────────────────────────────────────────────────────────
# 联系人 Tab
# ─────────────────────────────────────────────────────────────────

def _contacts_tab(db: ContactRepository):
    contacts = db.get_all_contacts()
    groups = db.get_all_groups()
    group_options = {g.id: g.group_name for g in groups}

    _ADD_KEY = "contacts_add_mode"

    col_h, col_btn = st.columns([3, 1])
    with col_h:
        st.caption(f"共 {len(contacts)} 位联系人")
    with col_btn:
        if st.button("+ 新建联系人", key="btn_add_contact", width="stretch", type="primary"):
            st.session_state[_ADD_KEY] = not st.session_state.get(_ADD_KEY, False)
            st.session_state.pop("contact_edit_id", None)

    # ── 新建表单 ──
    if st.session_state.get(_ADD_KEY) and not st.session_state.get("contact_edit_id"):
        with st.container(border=True):
            st.markdown("**新建联系人**")
            with st.form("form_add_contact", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    new_name = st.text_input("姓名 *", placeholder="张三")
                with c2:
                    new_email = st.text_input("邮箱 *", placeholder="zhang@example.com")
                new_note = st.text_input("备注", placeholder="部门 / 职位 / 其他")
                new_gids = st.multiselect(
                    "所属群组",
                    options=list(group_options.keys()),
                    format_func=lambda gid: group_options.get(gid, ""),
                )
                c_save, c_cancel = st.columns(2)
                with c_save:
                    submitted = st.form_submit_button("✅ 保存", type="primary", use_container_width=True)
                with c_cancel:
                    cancelled = st.form_submit_button("✖ 取消", use_container_width=True)

            if submitted:
                if not new_name.strip() or not new_email.strip():
                    st.error("姓名和邮箱不能为空")
                elif not _valid_email(new_email.strip()):
                    st.error("邮箱格式不正确")
                else:
                    try:
                        cid = db.create_contact(new_name.strip(), new_email.strip(), new_note.strip())
                        if new_gids:
                            db.set_contact_groups(cid, new_gids)
                        st.session_state[_ADD_KEY] = False
                        st.success(f"已添加联系人：{new_name.strip()}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"添加失败（邮箱可能已存在）：{e}")
            if cancelled:
                st.session_state[_ADD_KEY] = False
                st.rerun()

    # ── 编辑表单 ──
    edit_id = st.session_state.get("contact_edit_id")
    if edit_id:
        contact = db.get_contact(edit_id)
        if contact:
            with st.container(border=True):
                st.markdown(f"**编辑联系人：{contact.name}**")
                with st.form(f"form_edit_c_{edit_id}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        e_name = st.text_input("姓名 *", value=contact.name)
                    with c2:
                        e_email = st.text_input("邮箱 *", value=contact.email)
                    e_note = st.text_input("备注", value=contact.note or "")
                    cur_gids = [g.id for g in contact.groups]
                    e_gids = st.multiselect(
                        "所属群组",
                        options=list(group_options.keys()),
                        default=cur_gids,
                        format_func=lambda gid: group_options.get(gid, ""),
                    )
                    cs, cc = st.columns(2)
                    with cs:
                        e_sub = st.form_submit_button("✅ 保存", type="primary", use_container_width=True)
                    with cc:
                        e_can = st.form_submit_button("✖ 取消", use_container_width=True)

                if e_sub:
                    if not e_name.strip() or not e_email.strip():
                        st.error("姓名和邮箱不能为空")
                    elif not _valid_email(e_email.strip()):
                        st.error("邮箱格式不正确")
                    else:
                        try:
                            db.update_contact(edit_id, e_name.strip(), e_email.strip(), e_note.strip())
                            db.set_contact_groups(edit_id, e_gids)
                            st.session_state.pop("contact_edit_id", None)
                            st.success("联系人已更新")
                            st.rerun()
                        except Exception as e:
                            st.error(f"更新失败：{e}")
                if e_can:
                    st.session_state.pop("contact_edit_id", None)
                    st.rerun()

    # ── 联系人列表 ──
    if not contacts:
        st.info("暂无联系人，点击右上角「新建联系人」添加")
        return

    st.markdown(
        '<div style="display:grid;grid-template-columns:1.5fr 2fr 1.5fr 2.5rem 2.5rem;'
        'gap:8px;padding:4px 8px;color:#94A3B8;font-size:12px;font-weight:600;">'
        "<span>姓名</span><span>邮箱</span><span>群组</span><span></span><span></span></div>",
        unsafe_allow_html=True,
    )

    for c in contacts:
        group_names = "、".join(g.group_name for g in c.groups) if c.groups else "—"
        with st.container(border=True):
            row = st.columns([1.5, 2, 1.5, 0.4, 0.4])
            with row[0]:
                st.markdown(f"**{c.name}**")
                if c.note:
                    st.caption(c.note)
            with row[1]:
                st.markdown(
                    f'<span style="color:#475569;font-size:13px">{c.email}</span>',
                    unsafe_allow_html=True,
                )
            with row[2]:
                st.markdown(
                    f'<span style="color:#64748B;font-size:13px">{group_names}</span>',
                    unsafe_allow_html=True,
                )
            with row[3]:
                if st.button("✏️", key=f"edit_c_{c.id}", help="编辑", use_container_width=True):
                    st.session_state.contact_edit_id = c.id
                    st.session_state["contacts_add_mode"] = False
                    st.rerun()
            with row[4]:
                del_key = f"del_c_confirm_{c.id}"
                if st.session_state.get(del_key):
                    if st.button("✓", key=f"del_c_ok_{c.id}", type="primary",
                                 help="确认删除", use_container_width=True):
                        db.delete_contact(c.id)
                        st.session_state.pop(del_key, None)
                        st.rerun()
                else:
                    if st.button("🗑", key=f"del_c_{c.id}", help="删除", use_container_width=True):
                        st.session_state[del_key] = True
                        st.rerun()


# ─────────────────────────────────────────────────────────────────
# 群组 Tab
# ─────────────────────────────────────────────────────────────────

def _groups_tab(db: ContactRepository):
    groups = db.get_all_groups()
    _ADD_G_KEY = "groups_add_mode"

    col_h, col_btn = st.columns([3, 1])
    with col_h:
        st.caption(f"共 {len(groups)} 个群组")
    with col_btn:
        if st.button("+ 新建群组", key="btn_add_group", width="stretch", type="primary"):
            st.session_state[_ADD_G_KEY] = not st.session_state.get(_ADD_G_KEY, False)
            st.session_state.pop("group_edit_id", None)

    # ── 新建群组表单 ──
    if st.session_state.get(_ADD_G_KEY) and not st.session_state.get("group_edit_id"):
        with st.container(border=True):
            st.markdown("**新建群组**")
            with st.form("form_add_group", clear_on_submit=True):
                new_gname = st.text_input("群组名称 *", placeholder="技术组 / 销售团队 / ...")
                cg_sub, cg_can = st.columns(2)
                with cg_sub:
                    g_sub = st.form_submit_button("✅ 创建", type="primary", use_container_width=True)
                with cg_can:
                    g_can = st.form_submit_button("✖ 取消", use_container_width=True)

            if g_sub:
                if not new_gname.strip():
                    st.error("群组名称不能为空")
                else:
                    db.create_group(new_gname.strip())
                    st.session_state[_ADD_G_KEY] = False
                    st.success(f"已创建群组：{new_gname.strip()}")
                    st.rerun()
            if g_can:
                st.session_state[_ADD_G_KEY] = False
                st.rerun()

    # ── 编辑群组表单 ──
    edit_gid = st.session_state.get("group_edit_id")
    if edit_gid:
        group = db.get_group(edit_gid)
        if group:
            all_contacts = db.get_all_contacts()
            member_ids = [c.id for c in group.contacts]
            c_opts = {c.id: f"{c.name}  ({c.email})" for c in all_contacts}
            with st.container(border=True):
                st.markdown(f"**编辑群组：{group.group_name}**")
                with st.form(f"form_edit_g_{edit_gid}"):
                    eg_name = st.text_input("群组名称 *", value=group.group_name)
                    eg_members = st.multiselect(
                        "群组成员",
                        options=list(c_opts.keys()),
                        default=member_ids,
                        format_func=lambda cid: c_opts.get(cid, str(cid)),
                    )
                    gs, gc = st.columns(2)
                    with gs:
                        eg_sub = st.form_submit_button("✅ 保存", type="primary", use_container_width=True)
                    with gc:
                        eg_can = st.form_submit_button("✖ 取消", use_container_width=True)

                if eg_sub:
                    if not eg_name.strip():
                        st.error("群组名称不能为空")
                    else:
                        db.update_group(edit_gid, eg_name.strip())
                        cur_set = set(member_ids)
                        new_set = set(eg_members)
                        for cid in new_set - cur_set:
                            db.add_contact_to_group(cid, edit_gid)
                        for cid in cur_set - new_set:
                            db.remove_contact_from_group(cid, edit_gid)
                        st.session_state.pop("group_edit_id", None)
                        st.success("群组已更新")
                        st.rerun()
                if eg_can:
                    st.session_state.pop("group_edit_id", None)
                    st.rerun()

    # ── 群组列表 ──
    if not groups:
        st.info("暂无群组，点击右上角「新建群组」创建")
        return

    for g in groups:
        n = len(g.contacts)
        with st.container(border=True):
            row = st.columns([3, 1.5, 0.4, 0.4])
            with row[0]:
                st.markdown(f"**{g.group_name}**")
                if g.contacts:
                    preview = "、".join(c.name for c in g.contacts[:6])
                    if n > 6:
                        preview += f" 等 {n} 人"
                    st.caption(preview)
            with row[1]:
                st.caption(f"{n} 位成员")
            with row[2]:
                if st.button("✏️", key=f"edit_g_{g.id}", help="编辑群组", use_container_width=True):
                    st.session_state.group_edit_id = g.id
                    st.session_state[_ADD_G_KEY] = False
                    st.rerun()
            with row[3]:
                del_gkey = f"del_g_confirm_{g.id}"
                if st.session_state.get(del_gkey):
                    if st.button("✓", key=f"del_g_ok_{g.id}", type="primary",
                                 help="确认删除", use_container_width=True):
                        db.delete_group(g.id)
                        st.session_state.pop(del_gkey, None)
                        st.rerun()
                else:
                    if st.button("🗑", key=f"del_g_{g.id}", help="删除群组", use_container_width=True):
                        st.session_state[del_gkey] = True
                        st.rerun()


def _valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))
