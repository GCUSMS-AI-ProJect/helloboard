"""Check native curve interpolation, gaps and motion preferences in Chromium."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright, expect

OUT = Path(__file__).resolve().parent
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':900},reduced_motion='reduce')
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:8090/')
    expect(page.locator('#update-state')).to_have_text('实时更新')
    page.route('**/api/system*',lambda route:route.abort())
    # Block polling responses while exercising a controlled series.
    page.evaluate('''() => {
      HelloBoardCharts.pause(false);
      const path=document.querySelector('#usage-chart .series-primary');
      HelloBoardCharts.draw(path,[[2,160],[598,150]]);
    }''')
    expect(page.locator('#usage-chart animate')).to_have_count(0)
    page.emulate_media(reduced_motion='no-preference')
    page.evaluate('''() => HelloBoardCharts.draw(document.querySelector('#usage-chart .series-primary'),[[2,150],[300,100],[598,30]])''')
    animation=page.locator('#usage-chart .series-primary animate')
    expect(animation).to_have_count(1)
    expect(animation).to_have_attribute('dur','1.65s')
    # Both ends of the animated path move gradually; DOM base values retain the
    # real target. No fake samples or perpetual requestAnimationFrame loop.
    def end_y():
        return page.locator('#usage-chart .series-primary').evaluate('e=>e.getPointAtLength(e.getTotalLength()).y')
    initial=end_y()
    page.wait_for_timeout(450)
    middle=end_y()
    assert 30 < middle < initial <= 150,(initial,middle)
    expect(animation).to_have_count(0,timeout=2500)
    final=end_y()
    assert abs(final-30)<0.1,final
    # Curves never overshoot the range between genuine sample points.
    bounds=page.locator('#usage-chart .series-primary').evaluate('''e=>{
      const length=e.getTotalLength();const ys=Array.from({length:101},(_,i)=>e.getPointAtLength(length*i/100).y);
      return [Math.min(...ys),Math.max(...ys)];}''')
    assert bounds[0]>=29.9 and bounds[1]<=150.1,bounds
    # Missing samples break the line instead of connecting unknown history.
    page.evaluate('''() => HelloBoardCharts.draw(document.querySelector('#usage-chart .series-primary'),[[2,150],[180,100],null,[400,90],[598,30]])''')
    path=page.locator('#usage-chart .series-primary').get_attribute('d')
    assert path.count('M')==2,path
    page.emulate_media(reduced_motion='reduce')
    page.evaluate('''() => HelloBoardCharts.draw(document.querySelector('#usage-chart .series-primary'),[[2,160],[300,90],[598,50]])''')
    expect(page.locator('#usage-chart animate')).to_have_count(0)
    assert abs(end_y()-50)<0.1
    # Real polling still uses the same animation after resuming.
    page.emulate_media(reduced_motion='no-preference')
    page.unroute('**/api/system*')
    page.locator('#refresh-status').click()
    page.wait_for_selector('#usage-chart animate',timeout=7000,state='attached')
    page.screenshot(path=str(OUT/'system-curves.png'),full_page=True)
    assert not errors,errors
    report=dict(native_svg_motion=True,duration_seconds=1.65,initial_y=initial,middle_y=middle,final_y=final,
                no_overshoot=True,missing_data_gaps=True,reduced_motion_supported=True,js_errors=errors)
    (OUT/'chart-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    browser.close()
