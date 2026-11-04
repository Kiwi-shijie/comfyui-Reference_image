import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
const style=document.createElement("link");style.rel="stylesheet";style.href=new URL("./reference_image.css",import.meta.url).href;document.head.append(style);

const roles = [
  {key:"face", title:"👤 人物参考", field:"人物素材ID", upload:"人物上传文件"},
  {key:"scene", title:"🌄 场景参考", upload:"场景上传文件"},
  {key:"pose", title:"🧍 姿势参考", field:"姿势素材ID", upload:"姿势上传文件"},
  {key:"costume", title:"👗 服装参考", field:"服装素材ID", upload:"服装上传文件"},
];
const element = (tag, cls, text) => { const e=document.createElement(tag); e.className=cls; if(text)e.textContent=text; return e; };
const endpoint = path => api.apiURL(`/reference-image/${path}`);
async function readJson(response, label){
  if(response.status===404)throw Error(`${label}接口未加载：请完全退出并重启 ComfyUI，单独刷新网页无效。`);
  const type=response.headers.get("content-type")||"";
  if(!type.includes("application/json"))throw Error(`${label}返回了非 JSON 内容（HTTP ${response.status}），请查看 ComfyUI 启动日志。`);
  const data=await response.json();
  if(!response.ok)throw Error(data.error||`${label}失败（HTTP ${response.status}）`);
  return data;
}

app.registerExtension({
  name:"ReferenceImage.Composer",
  async beforeRegisterNodeDef(Node, data) {
    if(data.name!=="ReferenceImageComposer")return;
    const original=Node.prototype.onNodeCreated;
    Node.prototype.onNodeCreated=function(){
      original?.apply(this,arguments);
      const node=this;
      const widgets=Object.fromEntries((node.widgets||[]).map(w=>[w.name,w]));
      for(const role of roles)for(const field of [role.field,role.upload])if(field && widgets[field]){
        const w=widgets[field];w.type="reference-hidden";w.computeSize=()=>[0,-4];
        w.options??={};w.options.hidden=true;
      }
      const root=element("div","ri-root");
      root.append(element("div","ri-heading","🖼️ 参考图创作台"),element("div","ri-help","人物身份 · 环境场景 · 肢体姿势 · 服装细节"));
      const grid=element("div","ri-grid"); root.append(grid);
      const cards=[];
      const promptTitle=element("div","ri-prompt-title","✨ 整合提示词");
      const promptPreview=element("textarea","ri-prompt-preview");promptPreview.readOnly=true;
      promptPreview.placeholder="选择素材或填写创作需求后，点击刷新预览";
      const promptActions=element("div","ri-prompt-actions");
      const refreshButton=element("button","","刷新提示词");refreshButton.type="button";
      const copyButton=element("button","","复制提示词");copyButton.type="button";
      const promptStatus=element("span","","");promptActions.append(refreshButton,copyButton,promptStatus);
      refreshButton.onclick=refreshPreview;
      copyButton.onclick=async()=>{try{await navigator.clipboard.writeText(promptPreview.value);promptStatus.textContent="已复制";}catch{promptPreview.focus();promptPreview.select();promptStatus.textContent="按 Ctrl+C 复制";}};
      function refreshPreview(){
        const names={face:"人物",scene:"场景",pose:"姿势",costume:"服装"};
        const present=roles.filter(role=>widgets[role.upload]?.value||(role.field&&widgets[role.field]?.value)).map(role=>names[role.key]);
        const payload={present,"📝创作需求":widgets["📝创作需求"]?.value||"","🌄场景图用途":widgets["🌄场景图用途"]?.value||"仅环境场景","📷使用姿势视角":widgets["📷使用姿势视角"]?.value??true,"🧍姿势说明":widgets["🧍姿势说明"]?.value||""};
        promptStatus.textContent="正在整理…";
        api.fetchApi("/reference-image/prompt",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})
          .then(async response=>{const data=await readJson(response,"提示词");promptPreview.value=data.prompt;promptStatus.textContent=`${present.length} 张参考图`;})
          .catch(error=>{promptPreview.value="";promptStatus.textContent=error.message;});
      }
      const selectedImage=(role,id)=>endpoint(`image/${role.key}/${encodeURIComponent(id)}?size=thumb`);
      for(const role of roles){
        const card=element("section","ri-card");
        const head=element("div","ri-card-head");head.append(element("strong","",role.title));
        const pick=element("button","ri-pick","选择素材");pick.type="button";
        const upload=element("button","ri-upload","上传图片");upload.type="button";
        const file=element("input","");file.type="file";file.accept="image/png,image/jpeg,image/webp";file.hidden=true;
        const clear=element("button","ri-clear","清除");clear.type="button";
        head.append(pick,upload,clear);
        const preview=element("img","ri-preview");preview.alt=role.title;
        const empty=element("div","ri-empty","尚未选择参考图");
        const caption=element("div","ri-caption","");
        card.append(head,preview,empty,caption,file);grid.append(card);
        const render=()=>{
          const id=role.field?widgets[role.field]?.value:"";
          const uploaded=widgets[role.upload]?.value||"";
          preview.hidden=!id&&!uploaded;
          if(uploaded){preview.src=api.apiURL(`/view?${new URLSearchParams({filename:uploaded,subfolder:"reference-image",type:"input"})}`);}
          else if(id)preview.src=selectedImage(role,id);
          empty.hidden=!!id||!!uploaded;
          empty.textContent="选择图库素材或上传图片";
          caption.textContent=uploaded||id||"";
          clear.hidden=!id&&!uploaded;
          pick.hidden=role.key==="scene";
        };
        pick.onclick=()=>openPicker(role,widgets,render,refreshPreview);
        upload.onclick=()=>file.click();
        file.onchange=async()=>{
          const chosen=file.files?.[0];file.value="";if(!chosen)return;
          if(chosen.size>30*1024*1024){alert("图片不能超过 30MB");return;}
          const form=new FormData();form.append("image",chosen);form.append("type","input");form.append("subfolder","reference-image");form.append("overwrite","false");
          try{const response=await api.fetchApi("/upload/image",{method:"POST",body:form});const result=await readJson(response,"图片上传");widgets[role.upload].value=result.name;if(role.field)widgets[role.field].value="";render();refreshPreview();node.setDirtyCanvas?.(true,true);}
          catch(error){alert(error.message);}
        };
        clear.onclick=()=>{widgets[role.upload].value="";if(role.field)widgets[role.field].value="";node.setDirtyCanvas?.(true,true);render();refreshPreview();};
        cards.push(render);render();
      }
      root.append(promptTitle,promptPreview,promptActions,element("div","ri-footer","素材预览不会自动运行工作流。输出提示词和有序参考图，连接生图节点后运行。"));
      for(const name of ["pointerdown","wheel","keydown"])root.addEventListener(name,e=>e.stopPropagation());
      const dom=node.addDOMWidget("reference_cards","reference_cards",root,{serialize:false,getMinHeight:()=>800,getHeight:()=>800,hideOnZoom:false});
      dom.computeSize=w=>[Math.max(w||0,620),800];
      node.setSize([Math.max(node.size[0],620),Math.max(node.size[1],1120)]);
      for(const name of ["📝创作需求","🌄场景图用途","📷使用姿势视角","🧍姿势说明"]){
        const w=widgets[name];if(!w)continue;const originalCallback=w.callback;
        w.callback=function(){const value=originalCallback?.apply(this,arguments);queueMicrotask(refreshPreview);return value;};
      }
      queueMicrotask(refreshPreview);
      const configured=node.onConfigure;
      node.onConfigure=function(){const value=configured?.apply(this,arguments);queueMicrotask(()=>{node.setSize([Math.max(node.size[0],620),Math.max(node.size[1],1120)]);cards.forEach(f=>f());refreshPreview();});return value;};
    };
  }
});

async function openPicker(role,widgets,render,refreshPreview){
  const shade=element("div","ri-shade"), modal=element("div","ri-modal");
  const title=element("strong","",`${role.title} · 素材库`);
  const close=element("button","ri-close","关闭");close.type="button";close.onclick=()=>shade.remove();
  const bar=element("div","ri-modal-bar");bar.append(title,close);
  const search=element("input","ri-search");search.placeholder="搜索名称、类别或姿势视角";
  const status=element("div","ri-status","正在读取素材…");
  const gallery=element("div","ri-gallery");modal.append(bar,search,status,gallery);shade.append(modal);document.body.append(shade);
  shade.onclick=e=>{if(e.target===shade)shade.remove();};
  let items=[];
  try{
    const response=await api.fetchApi(`/reference-image/catalog/${role.key}`);
    const result=await readJson(response,"素材库");
    items=result.items;status.textContent=`共 ${items.length} 张，显示前 120 张；输入关键词筛选`;
    draw();
  }catch(error){status.textContent=error.message;}
  search.oninput=draw;
  function draw(){
    const q=search.value.trim().toLowerCase();
    const filtered=items.filter(i=>`${i.id} ${i.name} ${i.category} ${i.angle}`.toLowerCase().includes(q));
    gallery.replaceChildren();
    for(const item of filtered.slice(0,120)){
      const button=element("button","ri-tile");button.type="button";
      const image=element("img","");image.loading="lazy";image.src=endpoint(`image/${role.key}/${encodeURIComponent(item.id)}?size=thumb`);
      button.append(image,element("span","",`${item.name}${item.angle?" · "+item.angle:""}`));
      button.onclick=()=>{widgets[role.field].value=item.id;widgets[role.upload].value="";render();refreshPreview();shade.remove();};
      gallery.append(button);
    }
    if(!filtered.length)gallery.append(element("div","ri-status","没有匹配的素材"));
  }
}

