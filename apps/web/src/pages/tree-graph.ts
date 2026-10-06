import { LitElement, css, html, svg } from 'lit'
import { layoutFamilyBlocks } from './tree-layout'

export type TreeRelationshipData = { label:string; kind:string; certainty:'confirmed'|'descriptive'; reason:string }
export type TreePersonData = { id:string; display_name:string|null; sex:string|null; birth_label:string|null; death_label:string|null; is_hidden:boolean; is_root:boolean; relationship?:TreeRelationshipData; photo_url?:string|null }
export type TreeUnionData = { id:string; partner_one_id:string|null; partner_two_id:string|null; union_type:string|null }
export type TreeParentLinkData = { parent_id:string; child_id:string; union_id?:string|null; relationship_type:string }
export type TreeGraphData = { people:TreePersonData[]; unions:TreeUnionData[]; partner_links:TreeUnionData[]; parent_links:TreeParentLinkData[]; links:{parent_id:string;child_id:string}[]; relation_path:{person_ids:string[];labels:string[];common_ancestor_id:string|null}|null; continuations?:{source_person_id:string;count:number}[] }
export type LayoutOptions = { direction:'vertical'|'horizontal' }
export type CardMetrics = { width:number;height:number;lines:string[] }
export type NodePosition = { x:number;y:number;generation:number;width:number;height:number }
export type UnionPosition = { x:number;y:number;generation:number }
export type GenerationBand = { generation:number;label:string;x:number;y:number;width:number;height:number;alternate:boolean }
export type GraphPath = { kind:'partner'|'parent-child'|'expansion';from:string;to:string;d:string }
export type GraphLayout = { nodes:Record<string,NodePosition>;unions:Record<string,UnionPosition>;bands:GenerationBand[];paths:GraphPath[];width:number;height:number }

const COLUMN_GAP=28, FAMILY_GAP=52, ROW_GAP=132, HORIZONTAL_PADDING=240, VERTICAL_PADDING=72
const label=(p:TreePersonData)=>p.is_hidden?'Сведения скрыты':p.display_name||'Имя не указано'
const unique=(xs:string[])=>[...new Set(xs)]
export function cardMetrics(person:TreePersonData):CardMetrics { const lines:string[]=[]; let line=''; for(let word of label(person).split(/\s+/)){while(word.length>34){if(line){lines.push(line);line=''}lines.push(word.slice(0,34));word=word.slice(34)}const next=line?`${line} ${word}`:word;if(next.length>34&&line){lines.push(line);line=word}else line=next}if(line)lines.push(line);const longest=Math.max(...lines.map(x=>x.length),0);return {width:Math.min(420,Math.max(182,34+(person.photo_url?52:0)+longest*8)),height:Math.max(84,64+lines.length*20),lines} }

export function layoutTreeGraph(data:TreeGraphData,options:LayoutOptions):GraphLayout {
  const generation=generations(data), rows=new Map<number,TreePersonData[]>(), nodes:Record<string,NodePosition>={}, bounds=new Map<number,{y:number;height:number}>()
  for(const p of data.people){const g=generation.get(p.id)??0;rows.set(g,[...(rows.get(g)??[]),p])}
  const ordered=[...rows.keys()].sort((a,b)=>a-b);let y=VERTICAL_PADDING
  for(const g of ordered){const row=orderRow(rows.get(g)!,data);let x=HORIZONTAL_PADDING,h=76
    for(const p of row){const m=cardMetrics(p);nodes[p.id]={x,y,generation:g,width:m.width,height:m.height};x+=m.width+COLUMN_GAP;h=Math.max(h,m.height)}
    bounds.set(g,{y,height:h});y+=h+ROW_GAP
  }
  const unions=unionPositions(data,nodes)
  const width=Math.max(HORIZONTAL_PADDING*2,...Object.values(nodes).map(n=>n.x+n.width+HORIZONTAL_PADDING)),height=Math.max(VERTICAL_PADDING*2,...Object.values(nodes).map(n=>n.y+n.height+VERTICAL_PADDING))
  const bands=ordered.map((g,i)=>{const b=bounds.get(g)!;return {generation:g,label:g<0?`ПРЕДКИ · ${-g}`:g===0?'ЦЕНТР':`ПОТОМКИ · ${g}`,x:0,y:b.y-ROW_GAP/2,width,height:b.height+ROW_GAP,alternate:i%2===1}})
  if(options.direction==='vertical')return {nodes,unions,bands,paths:paths(data,nodes,unions,'vertical'),width,height}
  const horizontalNodes:Record<string,NodePosition>={},horizontalBounds=new Map<number,{x:number;width:number}>();let x=VERTICAL_PADDING
  for(const g of ordered){let y=HORIZONTAL_PADDING,w=76;for(const p of orderRow(rows.get(g)!,data)){const m=cardMetrics(p);horizontalNodes[p.id]={x,y,generation:g,width:m.width,height:m.height};y+=m.height+COLUMN_GAP;w=Math.max(w,m.width)}horizontalBounds.set(g,{x,width:w});x+=w+ROW_GAP}
  const horizontalUnions=unionPositions(data,horizontalNodes,'horizontal'),horizontalWidth=Math.max(VERTICAL_PADDING*2,...Object.values(horizontalNodes).map(n=>n.x+n.width+VERTICAL_PADDING)),horizontalHeight=Math.max(HORIZONTAL_PADDING*2,...Object.values(horizontalNodes).map(n=>n.y+n.height+HORIZONTAL_PADDING)),horizontalBands=ordered.map((g,i)=>{const b=horizontalBounds.get(g)!;return {generation:g,label:g<0?`ПРЕДКИ · ${-g}`:g===0?'ЦЕНТР':`ПОТОМКИ · ${g}`,x:b.x-ROW_GAP/2,y:0,width:b.width+ROW_GAP,height:horizontalHeight,alternate:i%2===1}})
  return {nodes:horizontalNodes,unions:horizontalUnions,bands:horizontalBands,paths:paths(data,horizontalNodes,horizontalUnions,'horizontal'),width:horizontalWidth,height:horizontalHeight}
}
function orderRow(people:TreePersonData[],data:TreeGraphData){
  const byId=new Map(people.map(person=>[person.id,person])),partners=new Map<string,string[]>()
  for(const union of data.unions){if(union.partner_one_id&&union.partner_two_id&&byId.has(union.partner_one_id)&&byId.has(union.partner_two_id)){partners.set(union.partner_one_id,[...(partners.get(union.partner_one_id)??[]),union.partner_two_id]);partners.set(union.partner_two_id,[...(partners.get(union.partner_two_id)??[]),union.partner_one_id])}}
  const used=new Set<string>(),ordered:TreePersonData[]=[]
  for(const person of [...people].sort((a,b)=>label(a).localeCompare(label(b),'ru'))){
    if(used.has(person.id))continue
    const nearby=(partners.get(person.id)??[]).map(id=>byId.get(id)).filter((partner):partner is TreePersonData=>Boolean(partner&&!used.has(partner.id))).sort((a,b)=>label(a).localeCompare(label(b),'ru'))
    const group=nearby.length>1?[nearby[0],person,...nearby.slice(1)]:[person,...nearby]
    ordered.push(...group)
    for(const member of group)used.add(member.id)
  }
  return ordered
}
function unionPositions(data:TreeGraphData,nodes:Record<string,NodePosition>,direction:LayoutOptions['direction']='vertical'){
  const unions:Record<string,UnionPosition>={}
  for(const union of data.unions){
    const a=union.partner_one_id?nodes[union.partner_one_id]:undefined,b=union.partner_two_id?nodes[union.partner_two_id]:undefined
    if(!a||!b||a.generation!==b.generation)continue
    if(direction==='horizontal'){
      const aCentre=a.y+a.height/2,bCentre=b.y+b.height/2
      const blocked=Object.entries(nodes).some(([id,node])=>id!==union.partner_one_id&&id!==union.partner_two_id&&node.generation===a.generation&&node.y+node.height/2>Math.min(aCentre,bCentre)&&node.y+node.height/2<Math.max(aCentre,bCentre))
      if(blocked)unions[union.id]={x:Math.min(a.x,b.x)-26,y:Math.min(a.y,b.y)-26,generation:a.generation}
      else {const top=a.y<=b.y?a:b;unions[union.id]={x:top.x+top.width/2,y:(aCentre+bCentre)/2,generation:a.generation}}
      continue
    }
    const aCentre=a.x+a.width/2,bCentre=b.x+b.width/2
    const blocked=Object.entries(nodes).some(([id,node])=>id!==union.partner_one_id&&id!==union.partner_two_id&&node.generation===a.generation&&node.x+node.width/2>Math.min(aCentre,bCentre)&&node.x+node.width/2<Math.max(aCentre,bCentre))
    if(blocked)unions[union.id]={x:Math.min(a.x,b.x)-26,y:Math.min(a.y,b.y)-26,generation:a.generation}
    else {const left=a.x<=b.x?a:b;unions[union.id]={x:(aCentre+bCentre)/2,y:left.y+left.height/2,generation:a.generation}}
  }
  return unions
}
function generations(data:TreeGraphData){const root=data.people.find(p=>p.is_root)??data.people[0],out=new Map<string,number>(root?[[root.id,0]]:[]);for(let pass=0;pass<data.people.length*3;pass++){let changed=false;for(const l of data.parent_links){const p=out.get(l.parent_id),c=out.get(l.child_id);if(p!==undefined&&c===undefined){out.set(l.child_id,p+1);changed=true}if(c!==undefined&&p===undefined){out.set(l.parent_id,c-1);changed=true}}for(const u of data.unions){if(!u.partner_one_id||!u.partner_two_id)continue;const a=out.get(u.partner_one_id),b=out.get(u.partner_two_id);if(a!==undefined&&b===undefined){out.set(u.partner_two_id,a);changed=true}if(b!==undefined&&a===undefined){out.set(u.partner_one_id,b);changed=true}}if(!changed)break}for(const p of data.people)out.set(p.id,out.get(p.id)??0);return out}
function paths(data:TreeGraphData,nodes:Record<string,NodePosition>,unions:Record<string,UnionPosition>,dir:LayoutOptions['direction']):GraphPath[]{const out:GraphPath[]=[];for(const u of data.unions){const a=u.partner_one_id?nodes[u.partner_one_id]:undefined,b=u.partner_two_id?nodes[u.partner_two_id]:undefined,hub=unions[u.id];if(a&&b&&hub)out.push({kind:'partner',from:u.partner_one_id!,to:u.partner_two_id!,d:partner(a,b,hub,dir)});const children=unique(data.parent_links.filter(l=>l.union_id===u.id).map(l=>l.child_id)).map(id=>nodes[id]).filter((n):n is NodePosition=>Boolean(n));if(hub&&children.length)out.push(...family(hub,children,dir).map((d,i)=>({kind:'parent-child' as const,from:u.id,to:`child-${i}`,d})))}for(const l of data.parent_links.filter(l=>!l.union_id||!unions[l.union_id])){const p=nodes[l.parent_id],c=nodes[l.child_id];if(p&&c)out.push({kind:'parent-child',from:l.parent_id,to:l.child_id,d:connector(p,c,dir)})}return out}
function partner(a:NodePosition,b:NodePosition,h:UnionPosition,d:LayoutOptions['direction']){if(d==='horizontal'){if(h.x<Math.min(a.x,b.x))return `M ${a.x} ${a.y+a.height/2} H ${h.x} V ${h.y} M ${h.x} ${h.y} V ${b.y+b.height/2} H ${b.x}`;const top=a.y<=b.y?a:b,bottom=top===a?b:a;return `M ${top.x+top.width/2} ${top.y+top.height} V ${h.y} H ${bottom.x+bottom.width/2} V ${bottom.y}`}if(h.y<Math.min(a.y,b.y))return `M ${a.x+a.width/2} ${a.y} V ${h.y} H ${h.x} M ${h.x} ${h.y} H ${b.x+b.width/2} V ${b.y}`;const left=a.x<=b.x?a:b,right=left===a?b:a;return `M ${left.x+left.width} ${left.y+left.height/2} H ${h.x} V ${right.y+right.height/2} H ${right.x}`}
function family(h:UnionPosition,cs:NodePosition[],d:LayoutOptions['direction']){if(d==='horizontal'){const bus=Math.min(...cs.map(c=>c.x))-26,centres=cs.map(c=>c.y+c.height/2);return [`M ${h.x} ${h.y} H ${bus} V ${Math.min(...centres)} M ${bus} ${Math.min(...centres)} V ${Math.max(...centres)}`,...cs.map(c=>`M ${bus} ${c.y+c.height/2} H ${c.x}`)]}const bus=Math.min(...cs.map(c=>c.y))-26,centres=cs.map(c=>c.x+c.width/2);return [`M ${h.x} ${h.y} V ${bus} H ${Math.min(...centres)} M ${Math.min(...centres)} ${bus} H ${Math.max(...centres)}`,...cs.map(c=>`M ${c.x+c.width/2} ${bus} V ${c.y}`)]}
function connector(p:NodePosition,c:NodePosition,d:LayoutOptions['direction']){return d==='horizontal'?`M ${p.x+p.width} ${p.y+p.height/2} H ${(p.x+p.width+c.x)/2} V ${c.y+c.height/2} H ${c.x}`:`M ${p.x+p.width/2} ${p.y+p.height} V ${(p.y+p.height+c.y)/2} H ${c.x+c.width/2} V ${c.y}`}

export class CatsTreeGraph extends LitElement {
  static properties={graph:{attribute:false},direction:{attribute:false},selectedId:{attribute:false},showBands:{attribute:false},collapseDistant:{attribute:false},compactDepth:{attribute:false},expandedBlockIds:{attribute:false}}
  declare graph:TreeGraphData|null;declare direction:LayoutOptions['direction'];declare selectedId:string|null;declare showBands:boolean;declare collapseDistant:boolean;declare compactDepth:number;declare expandedBlockIds:string[]
  constructor(){super();this.graph=null;this.direction='vertical';this.selectedId=null;this.showBands=true;this.collapseDistant=false;this.compactDepth=2;this.expandedBlockIds=[]}
  static styles=css`:host{display:block;min-width:100%;min-height:100%}.graph{position:relative}svg{display:block;overflow:visible}.band{fill:#f0f1ed}.band.alternate{fill:#f7f7f5}.band-label{fill:#71756f;font:700 11px Inter,system-ui,sans-serif;letter-spacing:.08em}.line{fill:none;stroke:#8c918a;stroke-width:1.4}.line.partner{stroke:#356650}.line.continuation{stroke-dasharray:4 4}.hub{fill:#fff;stroke:#8c918a;stroke-width:1.4}.card-layer{position:absolute;inset:0;pointer-events:none}.card,.continuation{position:absolute;box-sizing:border-box;display:block;border:1px solid #d7d8d2;border-radius:3px;padding:12px 14px;background:#fff;color:#171817;text-align:left;font-family:Inter,system-ui,sans-serif;cursor:pointer;pointer-events:auto}.card:hover,.card:focus-visible,.card.selected,.continuation:hover,.continuation:focus-visible{border:2px solid #24513f}.card.root{background:#24513f;border-color:#24513f;color:#fff}.card.hidden{background:#ececea;color:#171817}.continuation{min-height:28px;padding:4px 8px;font-size:12px;font-weight:700;white-space:nowrap}.person{display:flex;gap:10px;align-items:flex-start}img{width:38px;height:38px;border-radius:2px;object-fit:cover;flex:none}.copy{min-width:0}.eyebrow{display:block;color:#356650;font-size:10px;font-weight:700;letter-spacing:.08em}.root .eyebrow{color:#dcebe2}.name{display:block;margin-top:3px;font-size:14px;font-weight:700;line-height:18px;overflow-wrap:anywhere}.date{display:block;margin-top:4px;color:#6b6d69;font-size:12px}.root .date{color:#dcebe2}`
  render(){if(!this.graph?.people.length)return html`<p>У этого человека в архиве нет родственников.</p>`;const layout=layoutFamilyBlocks(this.graph,{direction:this.direction,collapseDistant:this.collapseDistant,compactDepth:this.compactDepth,expandedBlockIds:this.expandedBlockIds}),visibleHubs=new Set(layout.paths.filter(p=>p.kind==='parent-child'&&p.from.kind==='union').map(p=>p.from.id));return html`<div class="graph" style="width:${layout.width}px;height:${layout.height}px"><svg width="${layout.width}" height="${layout.height}" viewBox="0 0 ${layout.width} ${layout.height}" role="img" aria-label="Линии семейного дерева">${this.showBands?layout.bands.map(b=>svg`<g><rect class="band ${b.alternate?'alternate':''}" x="${b.x}" y="${b.y}" width="${b.width}" height="${b.height}"></rect><text class="band-label" x="24" y="${b.y+24}">${b.label}</text></g>`):''}${layout.paths.map(p=>svg`<path class="line ${p.kind}" d="${p.d}"></path>`)}${Object.entries(layout.unions).filter(([id])=>visibleHubs.has(id)).map(([,h])=>svg`<circle class="hub" cx="${h.x}" cy="${h.y}" r="4"></circle>`)}</svg><div class="card-layer">${this.graph.people.filter(p=>layout.nodes[p.id]).map(p=>this.card(p,layout.nodes[p.id]))}${layout.continuations.map(item=>html`<button class="continuation" style="left:${item.x}px;top:${item.y}px" aria-label="Показать ещё ${item.count} человек" @click=${(event:Event)=>this.expand(item.blockId,event)}>Показать ещё ${item.count}</button>`)}</div></div>`}
  private card(p:TreePersonData,n:NodePosition|undefined){if(!n)return null;const m=cardMetrics(p),role=p.is_root?'В ЦЕНТРЕ':p.relationship?.label.toUpperCase()??'УЧАСТНИК СЕМЬИ',dates=[p.birth_label,p.death_label].filter(Boolean).join(' – ')||'нет данных';return html`<button class="card ${p.is_root?'root':''} ${p.is_hidden?'hidden':''} ${this.selectedId===p.id?'selected':''}" data-person-id="${p.id}" style="left:${n.x}px;top:${n.y}px;width:${n.width}px;height:${n.height}px" aria-label="${label(p)}" @click=${()=>this.select(p.id)} @dblclick=${()=>this.center(p.id)}><span class="person">${p.photo_url?html`<img src="${p.photo_url}" alt="">`:''}<span class="copy"><span class="eyebrow">${role}</span><span class="name">${m.lines.map((line,i)=>html`${i?html`<br>`:''}${line}`)}</span><span class="date">${dates}</span></span></span></button>`}
  private expand(blockId:string,event:Event){event.stopPropagation();const source=this.graph ? layoutFamilyBlocks(this.graph,{direction:this.direction,collapseDistant:this.collapseDistant,compactDepth:this.compactDepth,expandedBlockIds:this.expandedBlockIds}).continuations.find(item=>item.blockId===blockId)?.sourcePersonId : undefined;this.dispatchEvent(new CustomEvent('continuation-select',{detail:{blockId,sourcePersonId:source},bubbles:true,composed:true}))}
  private select(id:string){this.dispatchEvent(new CustomEvent('person-select',{detail:{personId:id},bubbles:true,composed:true}))}private center(id:string){this.dispatchEvent(new CustomEvent('person-center',{detail:{personId:id},bubbles:true,composed:true}))}
}
customElements.define('cats-tree-graph',CatsTreeGraph)
