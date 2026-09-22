import { expect, test } from "bun:test";
import { CandidateBadges } from "../gnome/riwen-badge@riwen/badges.js";

function popup() {
  const labels: { visible: boolean; destroyed: boolean; destroy(): void }[] =
    [];
  const boxes = Array.from({ length: 3 }, () => ({
    _candidateLabel: { text: "" },
    add_child() {},
  }));
  const badges = new CandidateBadges(boxes, () => {
    const label = {
      visible: false,
      destroyed: false,
      destroy() {
        this.destroyed = true;
      },
    };
    labels.push(label);
    return label;
  });
  function update(candidates: string[], riwen = true) {
    // GNOME fills labels before the extension decorates them.
    candidates.forEach((text, i) => {
      const box = boxes[i];
      if (box) box._candidateLabel.text = text;
    });
    badges.update(candidates, riwen);
  }
  return { badges, boxes, labels, update };
}

test("decorates only the marked candidate without changing IBus strings", () => {
  const { boxes, labels, update } = popup();
  const candidates = ["这是怎么回事 〔Qwen〕", "这是怎忙会是"];
  update(candidates);
  expect(boxes[0]?._candidateLabel.text).toBe("这是怎么回事");
  expect(boxes[1]?._candidateLabel.text).toBe("这是怎忙会是");
  expect(labels.filter((label) => label.visible)).toHaveLength(1);
  expect(candidates[0]).toBe("这是怎么回事 〔Qwen〕");
});

test("navigation, shortened pages and engine switches clear stale badges", () => {
  const { boxes, labels, update } = popup();
  update(["程式 〔Qwen〕", "城市"]);
  update(["城市", "程式 〔Qwen〕"]);
  expect(labels.map((label) => label.visible)).toEqual([false, true]);
  update(["城"]);
  expect(labels.every((label) => !label.visible)).toBe(true);
  update(["程式 〔Qwen〕"], false);
  expect(boxes[0]?._candidateLabel.text).toBe("程式 〔Qwen〕");
  expect(labels.every((label) => !label.visible)).toBe(true);
});

test("disabling restores fallback and removes actors; reenable works", () => {
  const { boxes, labels, update, badges } = popup();
  update(["程式 〔Qwen〕"]);
  update(["程式 〔Qwen〕"]);
  expect(labels).toHaveLength(1);
  badges.destroy();
  expect(boxes[0]?._candidateLabel.text).toBe("程式 〔Qwen〕");
  expect(labels[0]?.destroyed).toBe(true);
  badges.destroy();

  const again = new CandidateBadges(boxes, () => ({
    visible: false,
    destroy() {},
  }));
  again.update([boxes[0]?._candidateLabel.text], true);
  expect(boxes[0]?._candidateLabel.text).toBe("程式");
  again.destroy();
});

test("disable does not overwrite labels changed by another extension", () => {
  const { boxes, badges, update } = popup();
  update(["程式 〔Qwen〕"]);
  const box = boxes[0];
  if (box) box._candidateLabel.text = "Changed elsewhere";
  badges.destroy();
  expect(boxes[0]?._candidateLabel.text).toBe("Changed elsewhere");
});
