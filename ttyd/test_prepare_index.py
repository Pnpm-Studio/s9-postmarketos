#!/usr/bin/env python3
"""Check the font wrapper also works when ttyd ends in a source-map comment."""
import runpy
import subprocess
import tempfile
from pathlib import Path

module = runpy.run_path(str(Path(__file__).with_name('prepare-index.py')))
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'font.ttf').write_bytes(b'test-font')
    module['main'].__globals__.update(
        stock_index=lambda: '<head></head><script type="text/javascript">'
                            'console.log("ttyd");\n//# sourceMappingURL=app.js.map</script>',
        FONT=str(root / 'font.ttf'), INDEX=root / 'index.html',
    )
    module['main']()
    html = (root / 'index.html').read_text()
    assert 'data:font/ttf;base64,dGVzdC1mb250' in html
    script = html.split('<script type="text/javascript">', 1)[1].split('</script>', 1)[0]
    (root / 'app.js').write_text(script)
    subprocess.run(['node', '--check', str(root / 'app.js')], check=True)
    assert 'app.js.map\nconst s9DashboardOrigin' in script
    check = r"""
const vm=require('vm'),fs=require('fs'),assert=require('assert');let handler,fits=0;
const parent={},term={options:{fontSize:15},fit(){fits++}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{
 URL,location:{href:'http://phone:7681/'},parent,console:{log(){}},
 document:{fonts:{load:()=>Promise.resolve()}},
 window:{term,addEventListener:(name,fn)=>{handler=fn}}
});
setImmediate(()=>{
 const send=(origin,source,size)=>handler({origin,source,data:{type:'s9-font-size',size}});
 send('http://other:8090',parent,16);assert.equal(term.options.fontSize,15);
 send('http://phone:8090',{},16);assert.equal(term.options.fontSize,15);
 send('http://phone:8090',parent,99);assert.equal(term.options.fontSize,15);
 send('http://phone:8090',parent,16);assert.equal(term.options.fontSize,16);assert.equal(fits,1);
});
"""
    subprocess.run(['node', '-e', check, str(root / 'app.js')], check=True)
print('ttyd font wrapper and source-map regression check passed')
