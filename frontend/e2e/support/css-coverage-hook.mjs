/* Opt-in collection over the existing proof worlds, including pages outside openPage.
   Coverage survives navigation; pseudo-state matches supplement Chromium's applied-rule counts.
   docs/design-shadcn-adoption.md#stylesheet-cleanup owns the deletion policy. */
import { mkdir, writeFile } from 'node:fs/promises';
import { gzipSync } from 'node:zlib';
import { resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const destination = process.env.COMPASS_CSS_COVERAGE;
if (destination) {
  const directory = resolve(destination);
  if (relative(root, directory).startsWith('..'))
    throw new Error('Coverage must stay in the worktree');
  await mkdir(directory, { recursive: true });
  const launch = chromium.launch.bind(chromium);
  let sequence = 0;
  chromium.launch = async (...args) => {
    const browser = await launch(...args);
    const newContext = browser.newContext.bind(browser);
    const flushes = new Set();
    browser.newContext = async (...options) => {
      const context = await newContext(...options);
      const newPage = context.newPage.bind(context);
      const pages = new Set();
      context.newPage = async (...pageOptions) => {
        const page = await newPage(...pageOptions);
        await page.coverage.startCSSCoverage({ resetOnNavigation: false });
        // Playwright discards anonymous Vite sheets. CDP retains those same rule counts
        // without rewriting the stylesheet under measurement to give it a source URL.
        const cdp = await context.newCDPSession(page);
        const sources = new Map();
        const reads = new Set();
        const usage = [];
        cdp.on('CSS.styleSheetAdded', ({ header }) => {
          const read = cdp
            .send('CSS.getStyleSheetText', { styleSheetId: header.styleSheetId })
            .then(({ text }) => sources.set(header.styleSheetId, { url: header.sourceURL, text }))
            .catch(() => undefined);
          reads.add(read);
        });
        await cdp.send('DOM.enable');
        await cdp.send('CSS.enable');
        await cdp.send('CSS.startRuleUsageTracking');
        const pseudoMatches = new Set();
        const evaluate = page.evaluate.bind(page);
        const sample = async () => {
          if (page.isClosed()) return;
          // Chromium forgets earlier document counts on navigation even when Playwright
          // retains their sources. Drain before navigation and after observable proof reads.
          const delta = await cdp.send('CSS.takeCoverageDelta');
          usage.push(...delta.coverage);
          const matches = await evaluate(() => {
            const matches = [];
            const walk = (rules) => {
              for (const rule of rules) {
                if (
                  rule.selectorText &&
                  /:(?:hover|focus|active|disabled|enabled|visited|before|after)|::/.test(
                    rule.selectorText,
                  )
                ) {
                  const base = rule.selectorText
                    .replace(/::[\w-]+(?:\([^)]*\))?/g, '')
                    .replace(
                      /:(?:hover|focus-visible|focus-within|focus|active|disabled|enabled|visited|before|after)\b/g,
                      '',
                    );
                  try {
                    if (document.querySelector(base)) matches.push(rule.selectorText);
                  } catch {
                    /* Unsupported selectors are named exceptions, never silently deleted. */
                  }
                }
                if (rule.cssRules) walk(rule.cssRules);
              }
            };
            for (const sheet of document.styleSheets) {
              try {
                walk(sheet.cssRules);
              } catch {
                /* Cross-origin assets cannot be queried. */
              }
            }
            return matches;
          }).catch(() => []);
          for (const selector of matches) pseudoMatches.add(selector);
        };
        page.evaluate = async (...values) => {
          const result = await evaluate(...values);
          await sample();
          return result;
        };
        for (const method of ['goto', 'reload']) {
          const original = page[method].bind(page);
          page[method] = async (...values) => {
            await sample();
            return original(...values);
          };
        }
        let flushed = false;
        const flush = async () => {
          if (flushed || page.isClosed()) return;
          flushed = true;
          await sample();
          const { ruleUsage } = await cdp.send('CSS.stopRuleUsageTracking');
          usage.push(...ruleUsage);
          await Promise.all(reads);
          const entries = [...sources].map(([id, source]) => ({
            ...source,
            ranges: usage
              .filter((rule) => rule.styleSheetId === id && rule.used)
              .map((rule) => ({ start: rule.startOffset, end: rule.endOffset })),
          }));
          const playwrightEntries = await page.coverage.stopCSSCoverage();
          entries.push(...playwrightEntries);
          await cdp.detach();
          const mode = process.env.COMPASS_E2E_BUNDLE || 'development';
          await writeFile(
            resolve(directory, `${mode}-${process.pid}-${++sequence}.json.gz`),
            gzipSync(
              JSON.stringify({
                mode,
                proof: process.argv[1],
                entries,
                pseudoMatches: [...pseudoMatches],
              }),
            ),
          );
        };
        pages.add(flush);
        flushes.add(flush);
        const close = page.close.bind(page);
        page.close = async (...values) => {
          await flush();
          return close(...values);
        };
        return page;
      };
      const close = context.close.bind(context);
      context.close = async (...values) => {
        for (const flush of pages) await flush();
        return close(...values);
      };
      return context;
    };
    const close = browser.close.bind(browser);
    browser.close = async (...values) => {
      for (const flush of flushes) await flush();
      return close(...values);
    };
    return browser;
  };
}
