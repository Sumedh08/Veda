import { describe, expect, it } from 'vitest';
import { linkifyCitationMarkers } from './citations';

describe('citation markers', () => {
  it('turns report citation markers into inspector links and preserves existing links', () => {
    expect(linkifyCitationMarkers('A finding [S1]. See [S2](https://doi.org/example).'))
      .toBe('A finding [S1](#veda-citation-S1). See [S2](https://doi.org/example).');
  });
});
