import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional

HEADER_RE = re.compile(r'(?im)^\s*(ChatGPT said|Assistant|You said|User)\s*:\s*')

FOOTER_CLEAN = "No file chosenNo file chosen\nChatGPT can make mistakes. Check important info. See Cookie Preferences."

def _normalize(s: str) -> str:
    # Lowercase, collapse whitespace, strip
    s = s.lower()
    # Strip HTML comments (if you sometimes paste prompts with comments)
    s = re.sub(r'<!--.*?-->', ' ', s, flags=re.S)
    # Normalize whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def _fingerprint(s: str, n: int = 200) -> str:
    """Use a short prefix to be resilient to small edits while avoiding huge scans."""
    return _normalize(s)[:n]

def _segment_turns(text: str) -> List[Tuple[str, str, int, int]]:
    """
    Splits transcript into segments tagged by role: 'user' or 'assistant'.
    Returns list of (role, content, start_pos, end_pos).
    """
    segs = []
    matches = list(HEADER_RE.finditer(text))
    for i, m in enumerate(matches):
        role_raw = m.group(1).lower()
        role = 'assistant' if 'chatgpt' in role_raw or 'assistant' in role_raw else 'user'
        start = m.end()
        end = matches[i+1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            segs.append((role, chunk, start, end))
    return segs

def _pair_user_assistant(segs: List[Tuple[str, str, int, int]]):
    """
    Make ordered (user_text, assistant_text, positions) pairs.
    We pair each user segment with the very next assistant segment.
    """
    pairs = []
    pending_user = None
    for role, chunk, start, end in segs:
        if role == 'user':
            pending_user = (chunk, start, end)
        elif role == 'assistant' and pending_user is not None:
            user_chunk, ustart, uend = pending_user
            pairs.append({
                'user': user_chunk,
                'assistant': chunk,
                'user_start': ustart,
                'assistant_start': start
            })
            pending_user = None
    return pairs

def extract_and_save_blocks(content: str, agents_list: List[Dict], out_dir: Path):
    """
    Route by agent **prompt** found inside the user turn; save the **following assistant turn**.
    The very first user→assistant pair in the transcript is **ignored** for routing,
    because it does not belong to any agent. It is still shown in the summary as (SKIPPED).

    Requirements:
      - agents_list[i] should include keys: 'name' and 'prompt'
      - The transcript contains alternating "You said/User:" and "ChatGPT said/Assistant:" headers.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # Clean and normalize newlines
    content = content.replace("\r\n", "\n")
    if FOOTER_CLEAN in content:
        content = content.replace(FOOTER_CLEAN, "")
    content = content.rstrip()

    segs = _segment_turns(content)
    if not segs:
        print("⚠️ No recognizable turns found (headers missing?).")
        return

    pairs_all = _pair_user_assistant(segs)
    if not pairs_all:
        print("⚠️ Found turns but no user→assistant pairs.")
        return

    # --- Skip the first pair for routing/assignment ---
    SKIP_FIRST = 1
    if len(pairs_all) <= SKIP_FIRST:
        # Only the skipped pair exists; write summary and return
        summary_lines = []
        for i, p in enumerate(pairs_all):
            excerpt = p['user'][:140].replace("\n", " ")
            skipped_tag = " (SKIPPED)" if i < SKIP_FIRST else ""
            summary_lines.append(f"[{i:02d}] USER EXCERPT:{skipped_tag} {excerpt} ...")
        (out_dir / "_block_summary.txt").write_text("\n".join(summary_lines), encoding="utf-8")
        return

    pairs = pairs_all[SKIP_FIRST:]  # routing set

    # Precompute normalized user texts for faster substring checks (routing set only)
    norm_user_texts = [_normalize(p['user']) for p in pairs]

    assigned_pair_idx = set()

    for agent in agents_list:
        name = agent.get('name') or agent.get('id') or "unknown_agent"
        prompt = agent.get('prompt') or agent.get('instructions') or ""
        if not prompt:
            print(f"⚠️ Agent '{name}' has no prompt; skipping.")
            continue

        pnorm = _normalize(prompt)
        pf = _fingerprint(prompt)  # shorter fingerprint is often enough

        # Find all pairs (within routing set) whose user turn contains the full prompt OR the fingerprint
        matched_idxs = []
        for i, user_norm in enumerate(norm_user_texts):
            if pnorm and pnorm in user_norm:
                matched_idxs.append(i)
            elif pf and pf in user_norm:
                matched_idxs.append(i)

        if not matched_idxs:
            print(f"⚠️ Prompt for '{name}' not found in any user turn. Writing placeholder.")
            (out_dir / f"{name}__UNMATCHED.txt").write_text(
                f"[UNMATCHED] Could not find this prompt in any 'You said' turn.\n\nPrompt (normalized excerpt):\n{pf}\n",
                encoding="utf-8"
            )
            continue

        # Use the LAST occurrence (assistant answer will be the last one)
        idx = matched_idxs[-1]

        # If that pair already assigned to another agent (rare), still allow but warn.
        if idx in assigned_pair_idx:
            print(f"ℹ️ Pair #{idx} already used by another agent. Proceeding for '{name}' (content may be duplicated).")
        assigned_pair_idx.add(idx)

        assistant_text = pairs[idx]['assistant']
        (out_dir / f"{name}.txt").write_text(assistant_text, encoding="utf-8")

    # Summary over ALL pairs; mark the skipped one
    summary_lines = []
    for i, p in enumerate(pairs_all):
        excerpt = p['user'][:140].replace("\n", " ")
        skipped_tag = " (SKIPPED)" if i < SKIP_FIRST else ""
        summary_lines.append(f"[{i:02d}] USER EXCERPT:{skipped_tag} {excerpt} ...")
    (out_dir / "_block_summary.txt").write_text("\n".join(summary_lines), encoding="utf-8")
