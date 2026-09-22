const MARKER = " 〔Qwen〕";

// Keep presentation separate from IBus data and candidate click handling.
export class CandidateBadges {
  constructor(boxes, createLabel) {
    this.entries = boxes.map((box) => ({
      box,
      badge: null,
      original: null,
      displayed: null,
    }));
    this.createLabel = createLabel;
  }

  update(candidates, isRiwen) {
    for (const [index, entry] of this.entries.entries()) {
      const text = candidates[index];
      const marked = isRiwen && text?.endsWith(MARKER);
      entry.original = null;
      entry.displayed = null;
      if (entry.badge) entry.badge.visible = false;
      if (!marked) continue;

      if (!entry.badge) {
        entry.badge = this.createLabel();
        entry.box.add_child(entry.badge);
      }
      entry.original = text;
      entry.displayed = text.slice(0, -MARKER.length);
      entry.box._candidateLabel.text = entry.displayed;
      entry.badge.visible = true;
    }
  }

  destroy() {
    for (const entry of this.entries) {
      // Restore the text fallback when disabling during a composition, but do
      // not overwrite a label another extension has since changed.
      if (
        entry.original !== null &&
        entry.box._candidateLabel.text === entry.displayed
      ) {
        entry.box._candidateLabel.text = entry.original;
      }
      entry.badge?.destroy();
    }
    this.entries = [];
  }
}
