# UI Redesign Spec — Meeting Agent

**Date**: 2026-05-20
**Status**: Approved
**Style**: Minimalist Business (极简商务风)

## Overview

Complete UI layer rewrite for Meeting Agent. Replace fragile `importlib` routing with Streamlit native `pages/` multipage, rebuild every page with integrated design tokens, and deliver a premium minimalist aesthetic.

---

## 1. Architecture

### 1.1 Routing

- **Before**: `app.py` uses `importlib.import_module()` + `getattr()` to dispatch pages. Any page import error crashes the entire app.
- **After**: Streamlit native `pages/` directory. `app.py` only sets global config, injects CSS, and renders the sidebar. Each page is a standalone `.py` file under `pages/`. A page crash only affects that page.

### 1.2 File Structure

```
ui/
  design.py          ← NEW: Design token constants (colors, radii, shadows, spacing)
  global_css.py      ← REWRITE: CSS injection using design tokens
  components.py      ← REWRITE: Reusable Streamlit components

app.py               ← REWRITE: Global config + sidebar only
pages/
  01_首页.py          ← NEW: home / dashboard
  02_上传会议.py       ← NEW: upload
  03_会议结果.py       ← NEW: result
  04_智能问答.py       ← NEW: chat
  05_历史记录.py       ← NEW: history
  06_数据统计.py       ← NEW: stats
```

### 1.3 Routes

| Page | Title | Icon | Description |
|------|-------|------|-------------|
| 01 | 首页 | ⌂ | Dashboard with hero, quick actions, stats, recent meetings |
| 02 | 上传会议 | ↑ | File upload, metadata form, process trigger |
| 03 | 会议结果 | 📄 | Three-column: todos, resolutions, minutes + transcript + Q&A |
| 04 | 智能问答 | 💬 | Standalone chat with meeting selector |
| 05 | 历史记录 | 🕐 | Searchable, filterable, paginated meeting list |
| 06 | 数据统计 | 📊 | Metrics + Plotly charts |

---

## 2. Design Tokens

### 2.1 Colors

| Token | Value | Usage |
|-------|-------|-------|
| `bg.base` | `#F8FAFC` | Page background |
| `bg.card` | `#FFFFFF` | Card/container background |
| `bg.hover` | `#F1F5F9` | Hover state |
| `bg.sidebar` | `#FAFBFC` | Sidebar background |
| `border.default` | `#E8ECF0` | Card/input borders |
| `border.hover` | `#CBD5E1` | Hover border |
| `text.primary` | `#0F172A` | Headings, body |
| `text.secondary` | `#475569` | Subtitle, metadata |
| `text.muted` | `#94A3B8` | Placeholder, captions |
| `accent.primary` | `#4F46E5` | Buttons, links, active indicators |
| `accent.hover` | `#4338CA` | Button hover |
| `accent.light` | `#EEF2FF` | Selected background |
| `accent.success` | `#059669` | Success states |
| `accent.warning` | `#D97706` | Todo badges |

### 2.2 Typography

- System font stack: `"Inter Display", system-ui, "PingFang SC", "Microsoft YaHei", sans-serif`
- Mono for timestamps: `"SF Mono", "Consolas", "Menlo", monospace`
- Inter Display loaded via Google Fonts (weights 400, 500, 600, 700)

### 2.3 Spacing & Radius

- Spacing scale: 4 / 8 / 12 / 16 / 20 / 24 / 32 / 48 / 64 (px)
- Border radius: 8px (inputs), 12px (buttons), 16px (cards)
- Sidebar width: 240px expanded, 64px collapsed

### 2.4 Shadows

- Card default: `0 1px 3px rgba(0,0,0,0.04)`
- Card hover: `0 4px 12px rgba(0,0,0,0.06)`
- No shadows on text inputs or buttons (flat design)

---

## 3. Page Layouts

### 3.1 Sidebar (app.py)

- Brand block at top: icon + "Meeting Agent" text
- 6 nav items, each with icon + Chinese label
- Active page: 3px indigo left border + indigo background tint
- Collapse toggle at bottom
- Scrollable if needed

### 3.2 Home (01_首页.py)

| Zone | Content |
|------|---------|
| Hero | Title "智能会议纪要助手" (34px, 800w), subtitle one line (16px, secondary) |
| CTA Cards | Two side-by-side cards: "上传会议" (primary) + "浏览历史" (secondary). 16px radius, 1px border, hover indigo border. Each has icon + title + description + arrow. |
| Stats Row | 4 metric columns in a bordered container: total meetings, pending todos, total processing time, completion rate. Number 32px bold, label 12px uppercase. |
| Recent Meetings | Horizontal card list, max 3. Each card: title, date, todo/decision pills, "查看 →" button. |

### 3.3 Upload (02_上传会议.py)

Single-column focused layout:
- File uploader zone with dashed border, generous padding, hover indigo border
- Title input (12px radius, placeholder text)
- Date/Time pickers in one row
- Export format select
- Advanced options in expander (template upload)
- Full-width primary submit button with estimated time caption
- Processing: progress bar + step indicator + live transcript preview

### 3.4 Result (03_会议结果.py)

- Top bar: back button + title/date + download button
- Overview bar: 4 metric columns (duration, type, category, todo count)
- Two-column cards: Todos (left) + Resolutions (right)
- Wide card: Minutes paper (max-width 740px centered, paper-like padding)
- Collapsible: Raw transcript with timestamped lines and search filter
- Bottom: Inline Q&A section with suggestion pills and text input

### 3.5 Chat (04_智能问答.py)

- Meeting selector dropdown at top
- Context info strip (todo count, resolution count)
- Chat bubble history: assistant bubbles (left-aligned, indigo left border, light indigo bg), user bubbles (right-aligned, gray bg)
- Suggestion pills row
- Chat input at bottom
- Clear conversation button

### 3.6 History (05_历史记录.py)

- Search input + duration filter dropdown + environment filter dropdown
- Count label
- Meeting card list (5 per page):
  - Each card: title, timestamp, duration label, environment label
  - Summary preview (120 chars)
  - Todo/decision count pills
  - View and Delete buttons (delete has confirmation step)
- Pagination: prev/next buttons + page indicator

### 3.7 Stats (06_数据统计.py)

- 4 metric cards row
- Duration distribution bar chart (left)
- Environment distribution pie chart (right)
- Monthly trend line chart (if >= 2 months of data)
- All charts: Plotly, indigo color scheme, transparent backgrounds

---

## 4. Component Library

Shared reusable components in `ui/components.py`:

| Component | Signature | Description |
|-----------|-----------|-------------|
| `metric_card` | (label, value, delta=None) | Unified stat display |
| `status_pill` | (text, variant="default") | Colored label pill |
| `empty_state` | (icon, title, description, action_label, action_key) | Empty placeholder with optional CTA |
| `error_card` | (title, description, retry_label, retry_key) | Error display card |
| `suggestion_pills` | (suggestions, prefix) | Row of clickable suggestion buttons |

---

## 5. Implementation Notes

- All colors referenced via `ui/design.py` constants, never hardcoded
- CSS injected once in `app.py` via `ui/global_css.py`
- Navigation: Streamlit native multi-page via `pages/` directory with numeric prefixes for ordering
- Page titles set via `st.set_page_config()` in each page file
- Sidebar rendered in `app.py` before page content
- Delete old UI files (`ui/home.py`, `ui/upload.py`, `ui/result.py`, `ui/chat.py`, `ui/history.py`, `ui/stats.py`) after new pages are verified
- Existing business logic (services, chains, agents, db) remains untouched
