export function computeFloatingMenuPosition(
  anchorEl,
  menuEl,
  { offset = 4, margin = 8 } = {},
) {
  if (!anchorEl) {
    return { top: `${margin}px`, left: `${margin}px` };
  }

  const anchorRect = anchorEl.getBoundingClientRect();
  const measured = Boolean(menuEl);
  const menuRect = measured
    ? menuEl.getBoundingClientRect()
    : { width: 0, height: 0 };

  let top = anchorRect.bottom + offset;
  let left = anchorRect.left;

  if (measured) {
    // Сдвиг по X/Y выполняем минимально, без резкого "flip" относительно якоря.
    const overflowRight = left + menuRect.width + margin - window.innerWidth;
    if (overflowRight > 0) left -= overflowRight;
    if (left < margin) left = margin;

    const overflowBottom = top + menuRect.height + margin - window.innerHeight;
    if (overflowBottom > 0) top -= overflowBottom;
    if (top < margin) top = margin;
  } else {
    left = Math.min(left, window.innerWidth - margin);
    left = Math.max(margin, left);
    top = Math.min(top, window.innerHeight - margin);
    top = Math.max(margin, top);
  }

  return {
    top: `${Math.round(top)}px`,
    left: `${Math.round(left)}px`,
  };
}
