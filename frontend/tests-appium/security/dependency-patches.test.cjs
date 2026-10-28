const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const extract = require('extract-zip');
const braces = require('braces');

// Small stored ZIPs with Unix file modes, including duplicate-name entries.
function zip(entries) {
  const locals = [], centrals = [];
  let offset = 0;
  for (const entry of entries) {
    const name = Buffer.from(entry.name), data = Buffer.from(entry.data);
    let crc = 0xffffffff;
    for (const byte of data) {
      crc ^= byte;
      for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
    }
    crc = (crc ^ 0xffffffff) >>> 0;
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(name.length, 26);
    locals.push(local, name, data);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE((3 << 8) | 20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(data.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(name.length, 28);
    central.writeUInt32LE(((entry.mode || 0o100644) * 65536) >>> 0, 38);
    central.writeUInt32LE(offset, 42);
    centrals.push(central, name);
    offset += local.length + name.length + data.length;
  }
  const directory = Buffer.concat(centrals), end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(directory.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, directory, end]);
}

async function fixture(t, entries) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'hillview-zip-security-'));
  t.after(() => fs.rm(root, {recursive: true, force: true}));
  const archive = path.join(root, 'input.zip'), dir = path.join(root, 'out');
  await fs.writeFile(archive, zip(entries));
  return {root, archive, dir};
}

test('regular files and nested directories extract normally', async t => {
  const {archive, dir} = await fixture(t, [{name: 'nested/file.txt', data: 'safe'}]);
  await extract(archive, {dir});
  assert.equal(await fs.readFile(path.join(dir, 'nested/file.txt'), 'utf8'), 'safe');
});

test('internal relative symlinks remain usable', async t => {
  const {archive, dir} = await fixture(t, [
    {name: 'link', data: 'target.txt', mode: 0o120777},
    {name: 'target.txt', data: 'safe'}
  ]);
  await extract(archive, {dir});
  assert.equal(await fs.readFile(path.join(dir, 'link'), 'utf8'), 'safe');
});

test('a symlink followed by a duplicate-name file cannot overwrite outside', async t => {
  const {root, archive, dir} = await fixture(t, [
    {name: 'link', data: '../outside.txt', mode: 0o120777},
    {name: 'link', data: 'overwritten'}
  ]);
  const outside = path.join(root, 'outside.txt');
  await fs.writeFile(outside, 'original');
  await assert.rejects(extract(archive, {dir}), /Out of bound|symlink/);
  assert.equal(await fs.readFile(outside, 'utf8'), 'original');
  await assert.rejects(fs.lstat(path.join(dir, 'link')), {code: 'ENOENT'});
});

test('absolute external symlink targets are rejected', async t => {
  const {root, archive, dir} = await fixture(t, []);
  await fs.writeFile(archive, zip([{name: 'link', data: path.join(root, 'outside'), mode: 0o120777}]));
  await assert.rejects(extract(archive, {dir}), /Out of bound/);
  await assert.rejects(fs.lstat(path.join(dir, 'link')), {code: 'ENOENT'});
});

test('symlinks through an existing external ancestor are rejected', async t => {
  const {root, archive, dir} = await fixture(t, [{name: 'link', data: 'escape/missing.txt', mode: 0o120777}]);
  await fs.mkdir(dir);
  await fs.mkdir(path.join(root, 'external'));
  await fs.symlink(path.join(root, 'external'), path.join(dir, 'escape'));
  await assert.rejects(extract(archive, {dir}), /Out of bound/);
});

test('links through an existing dangling external symlink are rejected', async t => {
  const {root, archive, dir} = await fixture(t, [{name: 'link', data: 'escape', mode: 0o120777}]);
  await fs.mkdir(dir);
  await fs.symlink(path.join(root, 'nonexistent-outside'), path.join(dir, 'escape'));
  await assert.rejects(extract(archive, {dir}), /Out of bound/);
  await assert.rejects(fs.lstat(path.join(dir, 'link')), {code: 'ENOENT'});
});

test('an existing final-component symlink is never overwritten', async t => {
  const {root, archive, dir} = await fixture(t, [{name: 'link', data: 'overwritten'}]);
  await fs.mkdir(dir);
  const outside = path.join(root, 'outside.txt');
  await fs.writeFile(outside, 'original');
  await fs.symlink(outside, path.join(dir, 'link'));
  await assert.rejects(extract(archive, {dir}), /Out of bound|symlink/);
  assert.equal(await fs.readFile(outside, 'utf8'), 'original');
});

test('normal brace expansion remains compatible', () => {
  assert.deepEqual(braces.expand('a{b,c}'), ['ab', 'ac']);
  assert.equal(braces.compile('a{b,c}'), 'a(b|c)');
});

test('deep string patterns fail at a controlled limit', () => {
  const pattern = '{'.repeat(2000) + 'a,b' + '}'.repeat(2000);
  for (const operation of ['parse', 'compile', 'expand']) {
    assert.throws(() => braces[operation](pattern), /Brace nesting exceeds security limit/);
  }
});

test('direct AST compilation, expansion and stringify are depth-bounded', () => {
  for (const operation of ['compile', 'expand', 'stringify']) {
    const ast = {type: 'root', nodes: []};
    let node = ast;
    for (let depth = 0; depth < 600; depth++) {
      const child = {type: 'brace', nodes: [], parent: node};
      node.nodes.push(child);
      node = child;
    }
    assert.throws(() => braces[operation](ast), /Brace nesting exceeds security limit/);
  }
});
