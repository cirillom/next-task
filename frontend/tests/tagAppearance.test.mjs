import assert from 'node:assert/strict';
import test from 'node:test';
import { tagAppearance } from '../src/lib/tagAppearance.ts';

test('tag backgrounds use their full configured color and readable text', () => {
  assert.deepEqual(tagAppearance('#123456'), { background: '#123456', foreground: '#ffffff' });
  assert.deepEqual(tagAppearance('#f9e984'), { background: '#f9e984', foreground: '#17231e' });
  assert.deepEqual(tagAppearance(null), { background: '#73847c', foreground: '#ffffff' });
  assert.deepEqual(tagAppearance('#777777'), { background: '#777777', foreground: '#ffffff' });
  assert.deepEqual(tagAppearance('#808080'), { background: '#808080', foreground: '#ffffff' });
  assert.deepEqual(tagAppearance('#999999'), { background: '#999999', foreground: '#17231e' });
  for (const color of ['#587b6a', '#5f6f8f', '#8a6f5a', '#7b658e', '#4f7f86', '#8c625e', '#6f7f4f', '#9a7048', '#536f83', '#8a6678', '#607b73', '#7d7150']) {
    assert.equal(tagAppearance(color).foreground, '#ffffff', color);
  }
  assert.deepEqual(tagAppearance('invalid'), tagAppearance(null));
});

test('tag text stays legible across dark, middle, and light colors', () => {
  const luminance = (color) => {
    const channels = [1, 3, 5].map((index) => {
      const value = parseInt(color.slice(index, index + 2), 16) / 255;
      return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  };
  for (const color of ['#000000', '#587b6a', '#73847c', '#777777', '#808080', '#d79b2f', '#ffffff']) {
    const { background, foreground } = tagAppearance(color);
    const values = [luminance(background), luminance(foreground)].sort((a, b) => b - a);
    assert.ok((values[0] + 0.05) / (values[1] + 0.05) >= 3.75, color);
  }
});
