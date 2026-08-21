import { cors } from './_lib.js';
export default async function handler(req,res){cors(res);if(req.method==='OPTIONS')return res.status(204).end();return res.status(200).json({ok:true,service:'youngdabang-review-live',time:new Date().toISOString()});}
