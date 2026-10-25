import test from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import {transform} from 'esbuild'
const source=await readFile(new URL('../src/lib/editor-content.ts',import.meta.url),'utf8')
const {code}=await transform(source,{loader:'ts',format:'esm'})
const {toEditorContent}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'))
test('generated plain text keeps separate paragraphs',()=>{
  assert.equal(toEditorContent('父亲在窑口。\n\n他把火罐放下。'),'\x3cp>父亲在窑口。</p><p>他把火罐放下。</p>')
})
test('plain text cannot introduce markup or entities',()=>{
  assert.equal(toEditorContent('火候 < 300 & 余火 > 0。'),'<p>火候 &lt; 300 &amp; 余火 &gt; 0。</p>')
})
test('saved rich text retains its formatting',()=>{
  const html='<h2>窑口</h2><p><strong>父亲</strong>回来了。</p>'
  assert.equal(toEditorContent(html),html)
})
test('blank lines do not become empty paragraphs',()=>{
  assert.equal(toEditorContent('\n\n窑火。\n \n回家。\n'),'<p>窑火。</p><p>回家。</p>')
  assert.equal(toEditorContent(''),'')
})
