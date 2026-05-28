"""
Direction-aware UI helpers for Gradio 6.

Provides:
- RTL CSS injection (rtl_css) and utility CSS (util_css)
- Inline alignment-button JavaScript (util_script)
- Unique ID generators for HTML headings, paragraphs, blocks,
  and Textbox components, with manual and auto-direction variants.
"""
from acestep.ui.gradio.i18n import language_directionality

# ---------------------------------------------------------------------------
# Internal counters for automatic unique IDs
# ---------------------------------------------------------------------------
_heading_id_counter = 0
_paragraph_id_counter = 0
_block_id_counter = 0
_textbox_id_counter = 0


def rtl_heading_id(suffix: str | None = None, align_right: bool = True) -> str:
    """Return a unique element ID for a ``gr.HTML`` container whose **headings** 
    (``h1-h6``) should be RTL-directed and optionally right-aligned.

    The returned ID starts with one of two prefixes:
    - ``"rtl-html-heading-align-"`` when *align_right* is ``True`` (default)
    - ``"rtl-html-heading-dir-"``  when *align_right* is ``False``

    The RTL CSS rules use attribute selectors to apply:
    - ``direction: rtl`` to both prefixes (always fixed)
    - ``text-align: right`` **only** to the ``align`` prefix

    It can safely be used in LTR/RTL contexts as universal fix for RTL cases - in 
    LTR cases unused selectors will simply match nothing.

    Parameters
    ----------
    suffix:
        Optional human-readable label (e.g. ``"description"``).
        If omitted, an auto-incremented number is used.
    align_right:
        If ``True`` (default), the heading is also right-aligned.
        If ``False``, only the text direction is fixed.

    Returns
    -------
    A unique string suitable for ``gr.HTML(..., elem_id=...)``.
    """
    global _heading_id_counter

    prefix = "rtl-html-heading-align-" if align_right else "rtl-html-heading-dir-"

    if suffix is not None:
        safe_suffix = suffix.strip().replace(" ", "-")
        return f"{prefix}{safe_suffix}"

    _heading_id_counter += 1
    return f"{prefix}{_heading_id_counter}"

def auto_heading_id(suffix: str | None = None) -> str:
    """Return a unique element ID for a ``gr.HTML`` container whose **headings**
    (``h1-h6``) should be (LTR/RTL)-directed and (Left/Right)-aligned automatically.

    The returned ID:
    - starts with ``"rtl-html-heading-align-"`` prefix when current language directionality of i18n is ``rtl``
    - is an empty string ``""`` when current language directionality of i18n is ``ltr``

    The RTL CSS rules use attribute selectors to apply:
    - ``direction: rtl`` and ``text-align: right`` to the ``align`` prefix
    
    It can safely be used in LTR/RTL contexts as universal fix for RTL cases - in
    LTR cases Gradio will render id="" on the component's outer HTML element.

    Parameters
    ----------
    suffix:
        Optional human-readable label (e.g. ``"description"``).
        If omitted, an auto-incremented number is used.

    Returns
    -------
    A unique string suitable for ``gr.HTML(..., elem_id=...)``.
    """
    if language_directionality() != 'rtl':
        return ""
    
    global _heading_id_counter

    prefix = "rtl-html-heading-align-"

    if suffix is not None:
        safe_suffix = suffix.strip().replace(" ", "-")
        return f"{prefix}{safe_suffix}"

    _heading_id_counter += 1
    return f"{prefix}{_heading_id_counter}"

def rtl_paragraph_id(suffix: str | None = None, align_right: bool = True) -> str:
    """Return a unique element ID for a ``gr.HTML`` container whose **paragraphs** 
    (``p``) should be RTL-directed and optionally right-aligned.

    The returned ID starts with one of two prefixes:
    - ``"rtl-html-para-align-"`` when *align_right* is ``True`` (default)
    - ``"rtl-html-para-dir-"``  when *align_right* is ``False``

    The RTL CSS rules use attribute selectors to apply:
    - ``direction: rtl`` to both prefixes (always fixed)
    - ``text-align: right`` **only** to the ``align`` prefix

    It can safely be used in LTR/RTL contexts as universal fix for RTL cases - in 
    LTR cases unused selectors will simply match nothing.

    Parameters
    ----------
    suffix:
        Optional human-readable label (e.g. ``"description"``).
        If omitted, an auto-incremented number is used.
    align_right:
        If ``True`` (default), the paragraph is also right-aligned.
        If ``False``, only the text direction is fixed.

    Returns
    -------
    A unique string suitable for ``gr.HTML(..., elem_id=...)``.
    """
    global _paragraph_id_counter

    prefix = "rtl-html-para-align-" if align_right else "rtl-html-para-dir-"

    if suffix is not None:
        safe_suffix = suffix.strip().replace(" ", "-")
        return f"{prefix}{safe_suffix}"

    _paragraph_id_counter += 1
    return f"{prefix}{_paragraph_id_counter}"

def auto_paragraph_id(suffix: str | None = None) -> str:
    """Return a unique element ID for a ``gr.HTML`` container whose **paragraphs**
    (``p``) should be (LTR/RTL)-directed and (Left/Right)-aligned automatically.

    The returned ID:
    - starts with ``"rtl-html-para-align-"`` prefix when current language directionality of i18n is ``rtl``
    - is an empty string ``""`` when current language directionality of i18n is ``ltr``

    The RTL CSS rules use attribute selectors to apply:
    - ``direction: rtl`` and ``text-align: right`` to the ``align`` prefix

    It can safely be used in LTR/RTL contexts as universal fix for RTL cases - in
    LTR cases Gradio will render id="" on the component's outer HTML element.

    Parameters
    ----------
    suffix:
        Optional human-readable label (e.g. ``"description"``).
        If omitted, an auto-incremented number is used.

    Returns
    -------
    A unique string suitable for ``gr.HTML(..., elem_id=...)``.
    """
    if language_directionality() != 'rtl':
        return ""
    
    global _paragraph_id_counter

    prefix = "rtl-html-para-align-"

    if suffix is not None:
        safe_suffix = suffix.strip().replace(" ", "-")
        return f"{prefix}{safe_suffix}"

    _paragraph_id_counter += 1
    return f"{prefix}{_paragraph_id_counter}"

def rtl_block_id(suffix: str | None = None, align_right: bool = True) -> str:
    """Return a unique element ID for a ``gr.HTML`` container whose
    **both headings and paragraphs** (``h1-h6`` and ``p``) should be RTL-directed
    and optionally right-aligned.

    The returned ID starts with one of two prefixes:
    - ``"rtl-html-block-align-"`` when *align_right* is ``True`` (default)
    - ``"rtl-html-block-dir-"``   when *align_right* is ``False``

    The RTL CSS rules use attribute selectors to apply:
    - ``direction: rtl`` to both prefixes (always fixed)
    - ``text-align: right`` **only** to the ``align`` prefix

    It can safely replace :func:`rtl_heading_id` and
    :func:`rtl_paragraph_id` - unused selectors will simply match nothing.
    It can safely be used in LTR/RTL contexts as universal fix for RTL cases - in
    LTR cases unused selectors will match nothing.

    Parameters
    ----------
    suffix:
        Optional human-readable label (e.g. ``"description"``).
        If omitted, an auto-incremented number is used.
    align_right:
        If ``True`` (default), the block's text is also right-aligned.
        If ``False``, only the text direction is fixed.

    Returns
    -------
    A unique string suitable for ``gr.HTML(..., elem_id=...)``.
    """
    global _block_id_counter

    prefix = "rtl-html-block-align-" if align_right else "rtl-html-block-dir-"

    if suffix is not None:
        safe_suffix = suffix.strip().replace(" ", "-")
        return f"{prefix}{safe_suffix}"

    _block_id_counter += 1
    return f"{prefix}{_block_id_counter}"

def auto_block_id(suffix: str | None = None) -> str:
    """Return a unique element ID for a ``gr.HTML`` container whose
    **both headings and paragraphs** (``h1-h6`` and ``p``) should be
    (LTR/RTL)-directed and (Left/Right)-aligned automatically.

    The returned ID:
    - starts with ``"rtl-html-block-align-"`` prefix when current language directionality of i18n is ``rtl``
    - is an empty string ``""`` when current language directionality of i18n is ``ltr``

    The RTL CSS rules use attribute selectors to apply:
    - ``direction: rtl`` and ``text-align: right`` to the ``align`` prefix

    It can safely replace :func:`auto_heading_id` and
    :func:`auto_paragraph_id` - unused selectors will simply match nothing.
    It can safely be used in LTR/RTL contexts as universal fix for RTL cases - in
    LTR cases Gradio will render id="" on the component's outer HTML element.

    Parameters
    ----------
    suffix:
        Optional human-readable label (e.g. ``"description"``).
        If omitted, an auto-incremented number is used.

    Returns
    -------
    A unique string suitable for ``gr.HTML(..., elem_id=...)``.
    """
    if language_directionality() != 'rtl':
        return ""
    
    global _block_id_counter

    prefix = "rtl-html-block-align-"

    if suffix is not None:
        safe_suffix = suffix.strip().replace(" ", "-")
        return f"{prefix}{safe_suffix}"

    _block_id_counter += 1
    return f"{prefix}{_block_id_counter}"

def ltr_textbox_id(suffix: str | None = None, align_left: bool = True) -> str:
    """Return a unique element ID for a ``gr.Textbox`` component whose
    **textarea** should be LTR-directed and optionally Left-aligned.

    The returned ID starts with one of two prefixes:
    - ``"ltr-textbox-align-"`` when *align_left* is ``True`` (default)
    - ``"ltr-textbox-dir-"``   when *align_left* is ``False``

    The UTIL CSS rules use attribute selectors to apply:
    - ``direction: ltr`` to both prefixes (always fixed)
    - ``text-align: left`` **only** to the ``align`` prefix

    It forces the initial text direction and alignment of the textarea,
    preventing Gradio's default direction-switching behavior for this component.
    If alignment buttons are present (via ``alignment-toggle`` class), the user
    can still manually override the alignment (via Align left/right toggle) and 
    direction (via Ctrl/Cmd + Left/Right Shift) after the page loads, Gaining
    full control over the textarea's bidirectional behavior.
    Since the LTR rules reside in ``util_css()`` (always injected), this ID will
    always apply LTR direction/alignment, regardless of language.  It is safe
    for any context.

    Parameters
    ----------
    suffix:
        Optional human-readable label (e.g. ``"description"``).
        If omitted, an auto-incremented number is used.
    align_left:
        If ``True`` (default), the textarea is also left-aligned.
        If ``False``, the textarea is right-aligned (LTR direction with
        right-alignment).

    Returns
    -------
    A unique string suitable for ``gr.Textbox(..., elem_id=...)``.
    """
    global _textbox_id_counter

    prefix = "ltr-textbox-align-" if align_left else "ltr-textbox-dir-"

    if suffix is not None:
        safe_suffix = suffix.strip().replace(" ", "-")
        return f"{prefix}{safe_suffix}"

    _textbox_id_counter += 1
    return f"{prefix}{_textbox_id_counter}"

def rtl_textbox_id(suffix: str | None = None, align_right: bool = True) -> str:
    """Return a unique element ID for a ``gr.Textbox`` component whose
    **textarea** should be RTL-directed and optionally Right-aligned.

    The returned ID starts with one of two prefixes:
    - ``"rtl-textbox-align-"`` when *align_right* is ``True`` (default)
    - ``"rtl-textbox-dir-"``   when *align_right* is ``False``

    The RTL CSS rules use attribute selectors to apply:
    - ``direction: rtl`` to both prefixes (always fixed)
    - ``text-align: right`` **only** to the ``align`` prefix

    It forces the initial text direction and alignment of the textarea,
    preventing Gradio's default direction-switching behavior for this component.
    If alignment buttons are present (via ``alignment-toggle`` class), the user
    can still manually override the alignment (via Align left/right toggle) and 
    direction (via Ctrl/Cmd + Left/Right Shift) after the page loads, Gaining
    full control over the textarea's bidirectional behavior.
    It can safely be used in any language context.  When the UI language is RTL,
    the RTL-specific rules in ``rtl_css()`` are applied; when the language is LTR,
    those rules are absent, so the ID has no effect.

    Parameters
    ----------
    suffix:
        Optional human-readable label (e.g. ``"description"``).
        If omitted, an auto-incremented number is used.
    align_right:
        If ``True`` (default), the textarea is also right-aligned.
        If ``False``, the textarea is left-aligned (RTL direction with
        left-alignment)

    Returns
    -------
    A unique string suitable for ``gr.Textbox(..., elem_id=...)``.
    """
    global _textbox_id_counter

    prefix = "rtl-textbox-align-" if align_right else "rtl-textbox-dir-"

    if suffix is not None:
        safe_suffix = suffix.strip().replace(" ", "-")
        return f"{prefix}{safe_suffix}"

    _textbox_id_counter += 1
    return f"{prefix}{_textbox_id_counter}"

def auto_textbox_id(suffix: str | None = None) -> str:
    """Return a unique element ID for a ``gr.Textbox`` component whose
    **textarea** should be (LTR/RTL)-directed and (Left/Right)-aligned automatically.

    The returned ID starts with one of two prefixes:
    - ``"ltr-textbox-align-"`` when current language directionality of i18n is ``ltr``
    - ``"rtl-textbox-align-"`` when current language directionality of i18n is ``rtl``

    The UTIL/RTL CSS rules use attribute selectors to apply:
    - ``direction: ltr`` and ``text-align: left`` to the ``ltr-textbox-align`` prefix
    - ``direction: rtl`` and ``text-align: right`` to the ``rtl-textbox-align`` prefix

    It forces the initial text direction and alignment of the textarea,
    preventing Gradio's default direction-switching behavior for this component.
    If alignment buttons are present (via ``alignment-toggle`` class), the user
    can still manually override the alignment (via Align left/right toggle) and 
    direction (via Ctrl/Cmd + Left/Right Shift) after the page loads, Gaining
    full control over the textarea's bidirectional behavior.
    It automatically selects the appropriate prefix (LTR or RTL) based on the
    current language.  When the language is LTR, the ID matches LTR rules in
    ``util_css()``; when RTL, it matches RTL rules in ``rtl_css()``.  Safe in
    both contexts.

    Parameters
    ----------
    suffix:
        Optional human-readable label (e.g. ``"description"``).
        If omitted, an auto-incremented number is used.

    Returns
    -------
    A unique string suitable for ``gr.Textbox(..., elem_id=...)``.
    """
    global _textbox_id_counter

    prefix = "ltr-textbox-align-" if language_directionality() != 'rtl' else "rtl-textbox-align-"

    if suffix is not None:
        safe_suffix = suffix.strip().replace(" ", "-")
        return f"{prefix}{safe_suffix}"

    _textbox_id_counter += 1
    return f"{prefix}{_textbox_id_counter}"

def util_script() -> str:
    """Return the JavaScript block that adds left- and right-alignment
    ``<span>`` controls to every ``gr.Textbox`` with the class
    ``alignment-toggle``.

    The script uses a ``MutationObserver`` to handle dynamically rendered
    Gradio components and marks processed wrappers to avoid duplicates.
    It should be injected into the ``head`` of the Gradio app.

    The returned string is a ``<script>...</script>`` tag ready for use.
    """
    return """
    <script>
    /*
    * Add left- and right-alignment buttons to every gr.Textbox that has
    * elem_classes=["alignment-toggle"].  The buttons are <span> elements
    * (not <button>) to avoid Gradio's aggressive label-hover styles.
    * A class "alignment-manual" is added to the textarea after any click,
    * preventing automatic RTL CSS from overriding the user's choice.
    */
    (function() {
        function addButtons(wrapper) {
            if (wrapper.dataset.alignmentAdded) return;
            wrapper.dataset.alignmentAdded = 'true';

            var label = wrapper.querySelector('label');
            if (!label) return;
            var infoSpan = label.querySelector('span[data-testid="block-info"]');
            if (!infoSpan) return;
            var textarea = wrapper.querySelector('textarea[data-testid="textbox"]');
            if (!textarea) return;

            // Apply initial direction/alignment if an ID prefix is present
            var prefix = wrapper.id;
            var isRtlPrefix = prefix.startsWith('rtl-textbox-align') || prefix.startsWith('rtl-textbox-dir');
            var isLtrPrefix = prefix.startsWith('ltr-textbox-align') || prefix.startsWith('ltr-textbox-dir');
            if (isRtlPrefix || isLtrPrefix) {
                if (isRtlPrefix) {
                    textarea.dir = 'rtl';
                    textarea.style.textAlign = prefix.startsWith('rtl-textbox-align') ? 'right' : 'left';
                } else {
                    textarea.dir = 'ltr';
                    textarea.style.textAlign = prefix.startsWith('ltr-textbox-align') ? 'left' : 'right';
                }
                textarea.classList.add('alignment-manual');
            }

            // Left-align button
            var leftBtn = document.createElement('span');
            leftBtn.innerHTML = '↤';
            leftBtn.title = 'Align left';
            leftBtn.classList.add('alignment-btn');
            leftBtn.setAttribute('role', 'button');
            leftBtn.setAttribute('tabindex', '0');
            leftBtn.setAttribute('aria-label', 'Align left');
            leftBtn.addEventListener('click', function(e) {
                e.preventDefault();
                textarea.dir = 'ltr';
                textarea.style.textAlign = 'left';
                textarea.classList.add('alignment-manual');
            });
            leftBtn.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    leftBtn.click();
                }
            });

            // Right-align button
            var rightBtn = document.createElement('span');
            rightBtn.innerHTML = '↦';
            rightBtn.title = 'Align right';
            rightBtn.classList.add('alignment-btn');
            rightBtn.setAttribute('role', 'button');
            rightBtn.setAttribute('tabindex', '0');
            rightBtn.setAttribute('aria-label', 'Align right');
            rightBtn.addEventListener('click', function(e) {
                e.preventDefault();
                textarea.dir = 'rtl';
                textarea.style.textAlign = 'right';
                textarea.classList.add('alignment-manual');
            });
            rightBtn.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    rightBtn.click();
                }
            });

            // Insert after the tooltip div (if present) to preserve tooltip hover trigger
            // Determine if there is a tooltip div immediately after the info span.
            // The tooltip is present when the next sibling is NOT the textarea's
            // input container (which always has the "input-container" class).
            var nextEl = infoSpan.nextElementSibling;
            var hasTooltip = nextEl && !nextEl.classList.contains('input-container');

            // Remove the order styles; they aren't needed since DOM order already matches
            leftBtn.style.order = '';
            rightBtn.style.order = '';

            if (hasTooltip) {
                nextEl.after(leftBtn, rightBtn);
            } else {
                infoSpan.after(leftBtn, rightBtn);
            }
        }

        // Process already-rendered textboxes
        document.querySelectorAll('.alignment-toggle').forEach(addButtons);

        // Watch for dynamically added ones
        var observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType !== 1) return;
                    if (node.classList && node.classList.contains('alignment-toggle')) {
                        addButtons(node);
                    }
                    (node.querySelectorAll ? node.querySelectorAll('.alignment-toggle') : []).forEach(addButtons);
                });
            });
        });
        observer.observe(document.body, { childList: true, subtree: true });
    })();
    </script>
    """

def util_css() -> str:
    """Return the CSS block for inline alignment buttons in ``gr.Textbox``.

    It styles the clickable ``<span>`` elements so they appear as small,
    unobtrusive buttons next to the textbox label.

    The returned string can be safely appended to the main Gradio CSS
    string at UI build time.
    """
    return """
    /* ----------------------------------- */
    /* -- Fix components text direction -- */
    /* ----------------------------------- */

    /* ---- HTML element ID prefixes ---- */
    /*
     * Targets both align-prefixed and dir-prefixed elements.
     * High specificity overrides Gradio's built-in LTR defaults.
     */
    /* ---- Textboxe (textareas) ---- */
    /* (except when manually overridden) */
    [id^="ltr-textbox-align"] textarea:not(.alignment-manual),
    [id^="ltr-textbox-dir"] textarea:not(.alignment-manual) {
        direction: ltr;
        unicode-bidi: embed;
        /* Keep text right-aligned unless align_left=True */
        text-align: right;
    }

    /* ----------------------------------- */
    /* -- Fix componenets reading order -- */
    /* ----------------------------------- */

    /* ---- HTML element ID prefixes ---- */
    /*
     * Targets only align-prefixed elements.
     * High specificity overrides Gradio's built-in LTR defaults.
     */
    /* ---- Textbox (textareas) right-alignment ---- */
    /* (except when manually overridden) */
    [id^="ltr-textbox-align"] textarea:not(.alignment-manual) {
        text-align: left;
    }

    /* ----------------------------------- */
    /* ------ Additional needed css ------ */
    /* ----------------------------------- */

    /* ---- Inline alignment buttons for Textboxes with class "alignment-toggle" ---- */
    .alignment-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 22px;
        height: 22px;
        margin: 0 2px;
        border: none;
        background: transparent;
        color: var(--body-text-color-subdued, #888);
        font-size: 14px;
        cursor: pointer;
        border-radius: 4px;
        transition: background 0.15s, color 0.15s;
        vertical-align: middle;
        user-select: none;
    }
    .alignment-btn:hover {
        background: var(--color-accent, #4a9eff);
        color: #fff;
    }
    """

def rtl_css() -> str:
    """Return the RTL CSS block if the current language is RTL, else ``""``.

    The CSS block fixes text direction and alignment for used Gradio 6 components
    without altering the overall LTR component placement.
    
    The returned string can be safely appended to the main Gradio CSS
    string at UI build time.
    """
    if language_directionality() != 'rtl':
        return ""


    # Apply bidirectional text direction for RTL languages (e.g. Farsi).
    # This prevents mixed RTL/LTR text from being scrambled inside Gradio's
    # component labels, buttons, tabs, markdown and tooltips blocks.
    # The selectors target only the text-bearing elements in Gradio 6,
    # leaving the overall component layout and alignment unchanged.
    #
    # Additionally, the tabs are shifted to the right (flex-direction: row-reverse),
    # the accordion toggle icon/text and checkbox/radio indicator order is swapped
    # alongside some extra fixes resulting in a more natural reading flow for RTL users.
    return """
    /* ----------------------------------- */
    /* -- Fix components text direction -- */
    /* ----------------------------------- */

    /* ---- HTML element ID prefixes ---- */
    /*
     * Targets both align-prefixed and dir-prefixed elements.
     * High specificity overrides Gradio's built-in LTR defaults.
     */
    /* ---- Heading ---- */
    [id^="rtl-html-heading-align"] h1,
    [id^="rtl-html-heading-align"] h2,
    [id^="rtl-html-heading-align"] h3,
    [id^="rtl-html-heading-align"] h4,
    [id^="rtl-html-heading-align"] h5,
    [id^="rtl-html-heading-align"] h6,
    [id^="rtl-html-heading-dir"] h1,
    [id^="rtl-html-heading-dir"] h2,
    [id^="rtl-html-heading-dir"] h3,
    [id^="rtl-html-heading-dir"] h4,
    [id^="rtl-html-heading-dir"] h5,
    [id^="rtl-html-heading-dir"] h6 {
        direction: rtl;
        unicode-bidi: embed;
    }
    /* ---- Paragraph ---- */
    [id^="rtl-html-para-align"] p,
    [id^="rtl-html-para-dir"] p {
        direction: rtl;
        unicode-bidi: embed;
    }
    /* ---- Block (headings + paragraphs) ---- */
    [id^="rtl-html-block-align"] h1,
    [id^="rtl-html-block-align"] h2,
    [id^="rtl-html-block-align"] h3,
    [id^="rtl-html-block-align"] h4,
    [id^="rtl-html-block-align"] h5,
    [id^="rtl-html-block-align"] h6,
    [id^="rtl-html-block-align"] p,
    [id^="rtl-html-block-dir"] h1,
    [id^="rtl-html-block-dir"] h2,
    [id^="rtl-html-block-dir"] h3,
    [id^="rtl-html-block-dir"] h4,
    [id^="rtl-html-block-dir"] h5,
    [id^="rtl-html-block-dir"] h6,
    [id^="rtl-html-block-dir"] p {
        direction: rtl;
        unicode-bidi: embed;
    }
    /* ---- Textboxe (textareas) ---- */
    /* (except when manually overridden) */
    [id^="rtl-textbox-align"] textarea:not(.alignment-manual),
    [id^="rtl-textbox-dir"] textarea:not(.alignment-manual) {
        direction: rtl;
        unicode-bidi: embed;
        /* Keep text left-aligned unless align_right=True */
        text-align: left;
    }

    /* ---- Labels in sliders, textboxes, dropdowns, etc. ---- */
    span[data-testid="block-info"] {
        direction: rtl !important;
        unicode-bidi: embed;
    }

    /* ---- Audio and File labels ---- */
    label[data-testid="block-label"] {
        direction: rtl !important;
        unicode-bidi: embed;
    }

    /* ---- Checkbox labels ---- */
    .label-text {
        direction: rtl;
        unicode-bidi: embed;
    }

    /* ---- Radio labels ---- */
    label[data-testid$="-radio-label"] span {
        direction: rtl;
        unicode-bidi: embed;
    }

    /* ---- Markdown blocks ---- */
    [data-testid="markdown"] {
        direction: rtl !important;
        unicode-bidi: embed;
        overflow-x: hidden;
    }

    /* ---- Toast messages ---- */
    .toast-body,
    .toast-message-text {
        direction: rtl;
        unicode-bidi: embed;
    }

    /* ---- Textarea (placeholders + input text) ---- */
    /* (reserved — specific textareas are now handled by the ID-prefix rules above) */
    /*
    textarea[data-testid="textbox"] {
        direction: rtl !important;
        unicode-bidi: embed;
        // Keep text left-aligned to match LTR UI elements (captions, paths, etc.) 
        text-align: left;
    }
    */

    /* ---- Info tooltips (for labels with data-testid="block-info") ---- */
    .has-info-container span[data-testid="block-info"] + div,
    .has-info-container span[data-testid="block-info"] + span {
        direction: rtl !important;
        unicode-bidi: embed;
    }
    /* ---- Info tooltips - force RTL on inner text blocks ---- */
    .has-info-container span[data-testid="block-info"] + div .prose,
    .has-info-container span[data-testid="block-info"] + div p {
        direction: rtl !important;
        unicode-bidi: embed;
    }

    /* ---- Info tooltips (for checkboxes) ---- */
    .has-info-container .checkbox-container + div {
        direction: rtl;
        unicode-bidi: embed;
    }

    /* ---- Help modal body (reserved, currently handled by Markdown rules) ---- */
    /*
    .help-modal-body {
        direction: rtl;
        unicode-bidi: embed;
    }
    */

    /* ---- All buttons (Tabs, Accordion toggles, Generate, etc.) ---- */
    /*
     * Inside buttons, this swaps the visual order of text and icons
     * (e.g., accordion arrow position on the left side of the label).
     */
    button {
        direction: rtl;
        unicode-bidi: embed;
    }

    /* ----------------------------------- */
    /* -- Fix componenets reading order -- */
    /* ----------------------------------- */

    /* ---- HTML element ID prefixes ---- */
    /*
     * Targets only align-prefixed elements.
     * High specificity overrides Gradio's built-in LTR defaults.
     */
    /* ---- Heading right-alignment ---- */
    [id^="rtl-html-heading-align"] h1,
    [id^="rtl-html-heading-align"] h2,
    [id^="rtl-html-heading-align"] h3,
    [id^="rtl-html-heading-align"] h4,
    [id^="rtl-html-heading-align"] h5,
    [id^="rtl-html-heading-align"] h6 {
        text-align: right;
    }
    /* ---- Paragraph right-alignment ---- */
    [id^="rtl-html-para-align"] p {
        text-align: right;
    }
    /* ---- Block (headings + paragraphs) right-alignment ---- */
    [id^="rtl-html-block-align"] h1,
    [id^="rtl-html-block-align"] h2,
    [id^="rtl-html-block-align"] h3,
    [id^="rtl-html-block-align"] h4,
    [id^="rtl-html-block-align"] h5,
    [id^="rtl-html-block-align"] h6,
    [id^="rtl-html-block-align"] p {
        text-align: right;
    }
    /* ---- Textbox (textareas) right-alignment ---- */
    /* (except when manually overridden) */
    [id^="rtl-textbox-align"] textarea:not(.alignment-manual) {
        text-align: right;
    }

    /* ---- Flip tabs to the right ---- */
    .tab-container {
        flex-direction: row-reverse;
    }

    /* ---- Flip checkbox indicator to the right ---- */
    .checkbox-container {
        flex-direction: row-reverse;
    }
    /* ---- Flip checkbox info tooltips to the right ---- */
    .has-info-container .checkbox-container + div {
        left: auto;
        right: 0;
    }

    /* ---- Flip radio indicator to the right ---- */
    label[data-testid$="-radio-label"] {
        flex-direction: row-reverse;
    }
    /* ---- Adjust indicator->text margin for radio ---- */
    /*
     * Mirror the radio LTR spacing: remove margin-left from the text span
     * and apply the same gap as margin-right (now between indicator and text).
     */
    label[data-testid$="-radio-label"] span {
        margin-left: 0;
        margin-right: 8px;
    }

    /* ---- Flip Info/Warning/Error toasts to the left ---- */
    .toast-wrap {
        left: 0;
        right: auto !important;
    }

    /* ---- Adjust text→SVG info icon margin for labels & checkboxes ---- */
    /*
    * Mirror the LTR spacing: the SVG icon uses a left margin to separate it
    * from the label text.  In RTL we zero that out and apply an identical
    * right margin, placing the space between the icon and the text again.
    */
    .has-info-container span[data-testid="block-info"]::after,
    .checkbox-container:has(+ div) .label-text::after {
        margin-left: 0;
        margin-right: 8px;
    }

    /* ---- Flip help button to the right ---- */
    .help-inline-container {
        direction: rtl;
        margin-left: auto !important;
        margin-right: 0 !important;
    }

    /* ---- Flip help modal close button to the left ---- */
    .help-modal-close {
        right: auto;
        left: 16px;
    }

    /* ---- Flip help modal list indentation to the right ---- */
    .help-modal-body ul {
        padding-left: 0 !important;
        padding-right: 20px !important;
    }

    /* ---- Flip help modal blockquote left border to the right ---- */
    .help-modal-body blockquote {
        border-left: none !important;
        border-right: 3px solid #888 !important;
        padding-left: 0 !important;
        padding-right: 10px !important;
    }

    """
