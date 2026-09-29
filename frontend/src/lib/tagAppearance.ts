const fallbackColor = '#73847c';

function luminance(color: string): number {
  const channels = [1, 3, 5].map((index) => {
    const channel = parseInt(color.slice(index, index + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}

export function tagAppearance(color: string | null): { background: string; foreground: string } {
  const background = color && /^#[0-9a-fA-F]{6}$/.test(color) ? color : fallbackColor;
  const brightness = luminance(background);
  // Muted midtones read as dark in this palette; white remains legible on them.
  const foreground = brightness <= 0.23
    ? '#ffffff'
    : (brightness + 0.05) / (luminance('#17231e') + 0.05) >= 4.5 ? '#17231e' : '#000000';
  return { background, foreground };
}
