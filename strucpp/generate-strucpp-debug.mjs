#!/usr/bin/env node
// RetroPLC: compile ST sources and generate debug artifacts in one pass.
// Adapted from RetroPLC_IDE/tools/generate-strucpp-debug.mjs.
// Usage: node generate-strucpp-debug.mjs <output-dir> <source-dir> [--lib-dir <dir> ...] [--no-default-libs]
import { createHash } from 'node:crypto';
import { renameSync } from 'node:fs';
import { readFile, lstat, mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { resolve, join, basename, dirname, relative, sep, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';

const strucppDir = fileURLToPath(new URL('./node_modules/strucpp/', import.meta.url));
const usage = 'Usage: node generate-strucpp-debug.mjs <output-dir> <source-dir> [--lib-dir <dir> ...] [--no-default-libs]';

async function main() {
  if (process.argv.slice(2).includes('--help')) { console.log(usage); return; }
  const [outputDir, sourceDir, ...options] = process.argv.slice(2);
  if (!outputDir || !sourceDir) throw new Error(usage);
  const libraryDirs = [];
  for (let i = 0; i < options.length; i++) {
    if (options[i] === '--no-default-libs') continue;
    if (options[i] !== '--lib-dir' || !options[i + 1]) {
      throw new Error(`Invalid option: ${options[i]}`);
    }
    libraryDirs.push(resolve(options[++i]));
  }

  const { compile, discoverSTFiles, discoverStlibs } = await import('strucpp/node');
  const sourceRoot = resolve(sourceDir);
  const sourcePaths = discoverSTFiles(sourceRoot)
    .filter(file => !relative(sourceRoot, file).toLowerCase().startsWith(`tests${sep}`));
  if (sourcePaths.length === 0) throw new Error(`No ST/IL sources found in ${sourceDir}`);
  const names = sourcePaths.map(file => basename(file));
  if (new Set(names).size !== names.length) {
    throw new Error('Duplicate source filenames across directories; STruC++ source labels would collide');
  }
  const sources = await Promise.all(sourcePaths.map(async file => ({
    fileName: basename(file), source: await readFile(file, 'utf8'),
  })));
  const [primary, ...additionalSources] = sources;
  const libraries = [...new Set(libraryDirs)].flatMap(dir =>
    discoverStlibs(dir).sort((left, right) => {
      const a = left.manifest.name;
      const b = right.manifest.name;
      return a < b ? -1 : a > b ? 1 : 0;
    }));
  const { version } = JSON.parse(await readFile(resolve(strucppDir, 'package.json'), 'utf8'));
  const md5 = createHash('md5').update(JSON.stringify({ version, sources, libraries })).digest('hex');
  const result = compile(primary.source, {
    fileName: primary.fileName,
    headerFileName: 'generated.hpp',
    additionalSources,
    libraries,
    md5,
  });
  for (const warning of result.warnings ?? []) console.warn('Warning:', warning);
  if (!result.success) {
    for (const error of result.errors ?? []) console.error('Error:', error);
    throw new Error('STruC++ compilation failed');
  }
  if (!result.headerCode || !result.cppFiles?.length) {
    throw new Error('STruC++ returned no generated header or translation units');
  }
  if (!result.debugTableCpp || result.debugMap?.version !== 2 ||
      result.debugMap.md5 !== md5 || !Array.isArray(result.debugMap.arrays) ||
      !Array.isArray(result.debugMap.leaves)) {
    throw new Error('STruC++ returned an incomplete debug map or pointer table');
  }
  const files = new Map([
    ['generated.hpp', result.headerCode],
    ['generated_debug.cpp', result.debugTableCpp],
    ['debug_map.json', JSON.stringify(result.debugMap, null, 2) + '\n'],
  ]);
  for (const { name, content } of result.cppFiles) {
    if (!name.endsWith('.cpp') || name.includes('/') || name.includes('\\') ||
        [...files.keys()].some(existing => existing.toLowerCase() === name.toLowerCase()) || !content) {
      throw new Error(`Invalid or duplicate STruC++ translation unit: ${name}`);
    }
    files.set(name, content);
  }
  const out = resolve(outputDir);
  // The output directory is owned exclusively by this generator.
  // Refuse an output directory that contains the source tree or compiler.
  for (const protectedPath of [sourceRoot, strucppDir, ...libraryDirs]) {
    const rel = relative(out, resolve(protectedPath));
    if (!rel || (!rel.startsWith(`..${sep}`) && rel !== '..' && !isAbsolute(rel))) {
      throw new Error(`Output directory must not contain source, compiler or library files: ${out}`);
    }
  }
  await publish(out, files);
  console.log(`Wrote ${result.cppFiles.length} C++ units and ${result.debugMap.leaves.length} debug symbols to ${out}`);
}

async function publish(out, files) {
  await mkdir(dirname(out), { recursive: true });
  const stage = await mkdtemp(join(dirname(out), '.strucpp-'));
  const generated = join(stage, 'new');
  const previous = join(stage, 'previous');
  let preserveBackup = false;
  try {
    await mkdir(generated);
    for (const [name, content] of files) {
      await writeFile(join(generated, name), content, { flag: 'wx' });
    }
    const existing = await lstat(out).catch(error => {
      if (error.code !== 'ENOENT') throw error;
    });
    if (existing && !existing.isDirectory()) {
      throw new Error(`Generated output path must be a directory: ${out}`);
    }
    if (existing) renameSync(out, previous);
    try {
      renameSync(generated, out);
    } catch (error) {
      if (existing) {
        preserveBackup = true;
        renameSync(previous, out);
        preserveBackup = false;
      }
      throw error;
    }
  } finally {
    if (!preserveBackup) await rm(stage, { recursive: true, force: true });
  }
}
main().catch(error => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
