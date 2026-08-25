import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import {
  POST_META,
  assertIndexMatchesDisk,
  blogPosts,
  postDateKey,
  postSlugsOnDisk,
} from './posts';
import { POST_IMAGES } from './postImages';

/**
 * The index used to be a hand-maintained array with nothing tying it to the
 * articles on disk, and both halves had drifted: two cards linked to
 * directories that never existed, two articles had no card. These are the
 * checks that would have caught that.
 */

const tmpDirs: string[] = [];

afterEach(() => {
  for (const dir of tmpDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function fakeBlogDir(slugs: string[], withoutMdx: string[] = []): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'blog-'));
  tmpDirs.push(dir);
  for (const slug of [...slugs, ...withoutMdx]) {
    fs.mkdirSync(path.join(dir, slug));
    if (!withoutMdx.includes(slug)) fs.writeFileSync(path.join(dir, slug, 'page.mdx'), '# post');
  }
  return dir;
}

describe('the index matches the filesystem', () => {
  it('every article has a card and every card has an article', () => {
    expect(() => blogPosts()).not.toThrow();
  });

  it('names an article that has no card', () => {
    const dir = fakeBlogDir([...POST_META.map((p) => p.slug), 'articulo-sin-tarjeta']);
    expect(() => assertIndexMatchesDisk(postSlugsOnDisk(dir))).toThrow(/articulo-sin-tarjeta/);
    expect(() => assertIndexMatchesDisk(postSlugsOnDisk(dir))).toThrow(/no card/);
  });

  it('names a card that has no article — the 404 that shipped', () => {
    const dir = fakeBlogDir(POST_META.map((p) => p.slug).slice(1));
    expect(() => assertIndexMatchesDisk(postSlugsOnDisk(dir))).toThrow(
      new RegExp(POST_META[0].slug),
    );
    expect(() => assertIndexMatchesDisk(postSlugsOnDisk(dir))).toThrow(/link to a 404/);
  });

  it('reports both directions at once', () => {
    const dir = fakeBlogDir([...POST_META.map((p) => p.slug).slice(1), 'huerfano']);
    try {
      assertIndexMatchesDisk(postSlugsOnDisk(dir));
      throw new Error('expected a drift error');
    } catch (e) {
      expect((e as Error).message).toMatch(/huerfano/);
      expect((e as Error).message).toMatch(new RegExp(POST_META[0].slug));
    }
  });

  it('a directory without a page.mdx is not an article', () => {
    const dir = fakeBlogDir(POST_META.map((p) => p.slug), ['solo-estilos']);
    expect(postSlugsOnDisk(dir)).not.toContain('solo-estilos');
    expect(() => assertIndexMatchesDisk(postSlugsOnDisk(dir))).not.toThrow();
  });
});

describe('cards', () => {
  it('has one per article with no duplicate slugs', () => {
    expect(new Set(POST_META.map((p) => p.slug)).size).toBe(POST_META.length);
  });

  it('every card has an illustration', () => {
    for (const { slug } of POST_META) expect(POST_IMAGES[slug]).toBeTypeOf('function');
  });

  it('has no illustration left over from a deleted card', () => {
    expect(Object.keys(POST_IMAGES).sort()).toEqual(POST_META.map((p) => p.slug).sort());
  });

  it('every card carries the copy a card needs', () => {
    for (const post of POST_META) {
      expect(post.title, post.slug).not.toHaveLength(0);
      expect(post.excerpt, post.slug).not.toHaveLength(0);
      expect(post.readTime, post.slug).toMatch(/^\d+ min$/);
    }
  });
});

describe('ordering', () => {
  it('parses Spanish dates', () => {
    expect(postDateKey('21 ago 2026')).toBe(20260821);
    expect(postDateKey('5 jul 2025')).toBe(20250705);
    expect(postDateKey('1 ene 2027')).toBeGreaterThan(postDateKey('31 dic 2026'));
  });

  it('rejects a date it cannot read rather than sorting it to the end', () => {
    expect(() => postDateKey('21 aug 2026')).toThrow(/D mmm YYYY/);
    expect(() => postDateKey('2026-08-21')).toThrow(/D mmm YYYY/);
  });

  it('every card has a readable date', () => {
    for (const post of POST_META) expect(() => postDateKey(post.date), post.slug).not.toThrow();
  });

  it('renders newest first', () => {
    const keys = blogPosts().map((p) => postDateKey(p.date));
    expect(keys).toEqual([...keys].sort((a, b) => b - a));
  });

  it('keeps the declared order for posts sharing a date', () => {
    const posts = blogPosts();
    const shared = posts.filter((p) => p.date === posts[0].date).map((p) => p.slug);
    const declared = POST_META.filter((p) => p.date === posts[0].date).map((p) => p.slug);
    expect(shared).toEqual(declared);
  });
});
