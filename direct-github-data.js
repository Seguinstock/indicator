const STOCK_DATA_RAW_BASE='https://raw.githubusercontent.com/Seguinstock/indicator/main/';
const STOCK_ORIGINAL_FETCH=window.fetch.bind(window);

window.fetch=function(input,init){
  try{
    const raw=typeof input==='string'?input:input?.url;
    if(raw){
      const u=new URL(raw,window.location.href);
      const path=u.pathname.replace(/^\/indicator\//,'').replace(/^\//,'');
      if(path.startsWith('config/')||path.startsWith('data/')){
        const direct=new URL(STOCK_DATA_RAW_BASE+path);
        direct.searchParams.set('_',Date.now());
        return STOCK_ORIGINAL_FETCH(direct.toString(),{...(init||{}),cache:'no-store'});
      }
    }
  }catch(e){}
  return STOCK_ORIGINAL_FETCH(input,init);
};
