# -*- coding: utf-8 -*-
"""
S4 Binary Evaluation: Compare frozen LLM output against MINDMAP_TRACE_EVAL.md standard answers.

Binary scoring rules:
- S4 = 1 if: central topic correct AND all L1 branches covered (>=90% recall)
  AND >=90% L2 knowledge points covered AND >=90% parent-child correct AND no fabricated L1
- S4 = 0 otherwise
"""
import json
import os
import re

OUTPUT_DIR = "d:/knowledge bar/artifacts/mindmap-trace-eval/run_binary"

STANDARD_ANSWERS = {
    "T01": {
        "root": "AI\u4ea7\u54c1\u7ecf\u7406\u80fd\u529b\u6a21\u578b",
        "branches": [
            {"text": "\u5c97\u4f4d\u5b9a\u4f4d", "children": ["\u8fde\u63a5\u7528\u6237\u3001\u4ea7\u54c1\u4e0eAI\u6280\u672f", "\u5224\u65ad\u9700\u6c42\u662f\u5426\u9002\u5408AI", "\u5e73\u8861\u4ef7\u503c\u3001\u6280\u672f\u4e0e\u6210\u672c"]},
            {"text": "\u4ea7\u54c1\u80fd\u529b", "children": ["\u5e02\u573a\u4e0e\u7528\u6237\u7814\u7a76", "\u9700\u6c42\u5206\u6790\u4e0e\u7ade\u54c1\u5206\u6790", "\u4ea7\u54c1\u3001\u6d41\u7a0b\u4e0e\u539f\u578b\u8bbe\u8ba1", "\u4e0a\u7ebf\u8fed\u4ee3"]},
            {"text": "AI\u6280\u672f\u8ba4\u77e5", "children": ["\u5927\u8bed\u8a00\u6a21\u578b\u4e0ePrompt", "RAG\u4e0eAgent", "Embedding\u4e0e\u5411\u91cf\u6570\u636e\u5e93", "\u6a21\u578b\u5fae\u8c03"]},
            {"text": "\u98ce\u9669\u4e0e\u89e3\u51b3\u673a\u5236", "children": ["\u5e7b\u89c9\u4e0e\u8f93\u51fa\u4e0d\u7a33\u5b9a", "\u4e0a\u4e0b\u6587\u548c\u54cd\u5e94\u901f\u5ea6\u9650\u5236", "\u7ed3\u6784\u5316\u8f93\u51fa\u4e0e\u6821\u9a8c", "\u91cd\u8bd5\u4e0e\u4eba\u5de5\u786e\u8ba4"]},
            {"text": "\u4ea7\u54c1\u8bc4\u4f30", "children": ["\u5b8c\u6210\u7387\u3001\u51c6\u786e\u7387\u4e0e\u91c7\u7eb3\u7387", "\u54cd\u5e94\u65f6\u95f4\u4e0e\u8c03\u7528\u6210\u672c", "\u7559\u5b58\u7387\u4e0e\u6ee1\u610f\u5ea6", "\u5b89\u5168\u3001\u9690\u79c1\u4e0e\u53ef\u89e3\u91ca\u6027"]},
            {"text": "\u56e2\u961f\u534f\u4f5c", "children": ["\u7b97\u6cd5\u56e2\u961f", "\u540e\u7aef\u56e2\u961f", "\u524d\u7aef\u4e0e\u8bbe\u8ba1\u56e2\u961f", "\u8fd0\u8425\u56e2\u961f"]},
        ],
    },
    "T02": {
        "root": "AI\u6c42\u804c\u5206\u6790\u4ea7\u54c1\u5f00\u53d1",
        "branches": [
            {"text": "\u9700\u6c42\u5b9a\u4e49", "children": ["\u76ee\u6807\u7528\u6237\uff1a\u7f3a\u5c11\u6c42\u804c\u7ecf\u9a8c\u7684\u5927\u5b66\u751f", "\u75db\u70b9\uff1a\u770b\u4e0d\u61c2\u5c97\u4f4d\u91cd\u70b9", "\u75db\u70b9\uff1a\u65e0\u6cd5\u5224\u65ad\u5339\u914d\u5ea6", "\u4ef7\u503c\uff1a\u7406\u89e3\u5c97\u4f4d\u5e76\u83b7\u5f97\u884c\u52a8\u5efa\u8bae"]},
            {"text": "\u8d44\u6599\u51c6\u5907", "children": ["\u5c97\u4f4d\u63cf\u8ff0\u4e0e\u5b66\u751f\u7b80\u5386", "\u62db\u8058\u8981\u6c42\u4e0e\u8bc4\u4ef7\u6807\u51c6", "\u9762\u8bd5\u95ee\u9898\u4e0e\u6d4b\u8bd5\u6837\u672c", "\u9690\u79c1\u8131\u654f"]},
            {"text": "V0\u529f\u80fd", "children": ["\u7c98\u8d34JD\u4e0e\u586b\u5199\u80cc\u666f", "JD\u89e3\u6790\u4e0e\u7ecf\u5386\u6bd4\u8f83", "\u5339\u914d\u5ea6\u3001\u4f18\u52bf\u4e0e\u4e0d\u8db3", "\u7b80\u5386\u3001\u6c9f\u901a\u3001\u9762\u8bd5\u548c\u884c\u52a8\u5efa\u8bae"]},
            {"text": "V0\u8fb9\u754c", "children": ["\u4e0d\u652f\u6301OCR", "\u4e0d\u652f\u6301\u94fe\u63a5\u6293\u53d6", "\u4e0d\u652f\u6301\u5c97\u4f4d\u63a8\u8350", "\u4e0d\u652f\u6301\u81ea\u52a8\u6295\u9012"]},
            {"text": "\u7cfb\u7edf\u5206\u5de5", "children": ["\u524d\u7aef", "\u540e\u7aef", "AI\u6a21\u5757", "\u6570\u636e\u5e93"]},
            {"text": "\u6d4b\u8bd5\u4e0e\u4e0a\u7ebf", "children": ["\u5f02\u5e38\u8f93\u5165\u6d4b\u8bd5", "\u5355\u5143\u4e0e\u63a5\u53e3\u6d4b\u8bd5", "\u6d4f\u89c8\u5668\u9a8c\u6536", "\u5c0f\u8303\u56f4\u4e0a\u7ebf\u4e0e\u8fed\u4ee3"]},
        ],
    },
    "T03": {
        "root": "\u601d\u7ef4\u5bfc\u56feAgent V0\u4f1a\u8bae\u7ed3\u8bba",
        "branches": [
            {"text": "\u4ea7\u54c1\u4f53\u9a8c", "children": ["\u5c55\u793a\u6267\u884c\u72b6\u6001", "\u6269\u5927\u5bfc\u56fe\u533a\u57df", "\u51cf\u5c11\u8282\u70b9\u989c\u8272"]},
            {"text": "\u65e7\u6a21\u5757\u95ee\u9898", "children": ["\u72b6\u6001\u683c\u5f0f\u6df7\u4e71", "\u524d\u7aef\u4e0e\u6570\u636e\u5e93\u4e0d\u4e00\u81f4", "\u5220\u9664\u5e76\u91cd\u6784"]},
            {"text": "\u65b0\u6570\u636e\u7ed3\u6784", "children": ["\u8282\u70b9\u4e0e\u7236\u8282\u70b9ID", "\u6587\u5b57\u3001\u5c42\u7ea7\u548c\u987a\u5e8f", "\u539f\u6587\u6765\u6e90"]},
            {"text": "Agent\u804c\u8d23", "children": ["Python\uff1a\u6e05\u6d17\u3001\u6821\u9a8c\u548c\u8fde\u7ebf", "LLM\uff1a\u7406\u89e3\u3001\u63d0\u53d6\u3001\u5206\u7c7b\u548c\u4fee\u590d"]},
            {"text": "\u8c03\u7528\u9650\u5236", "children": ["\u6b63\u5e38\u4e00\u6b21\u4e3b\u8981\u8c03\u7528", "\u6700\u591a\u4fee\u590d\u4e24\u6b21"]},
            {"text": "\u6d4b\u8bd5\u4e0e\u89c6\u89c9", "children": ["\u5f02\u5e38\u3001\u63a5\u53e3\u548c\u6d4f\u89c8\u5668\u6d4b\u8bd5", "\u7f29\u653e\u3001\u4e0b\u8f7d\u548c\u5237\u65b0\u6062\u590d", "\u7b80\u6d01\u4f46\u4e0d\u590d\u5236\u54c1\u724c"]},
            {"text": "\u8ba1\u5212\u4e0e\u5206\u5de5", "children": ["\u7b2c\u4e00\u5468\uff1a\u6a21\u578b\u3001\u5de5\u5177\u3001\u63a5\u53e3", "\u7b2c\u4e8c\u5468\uff1a\u9875\u9762\u3001\u6e32\u67d3", "\u7b2c\u4e09\u5468\uff1a\u6d4b\u8bd5\u3001\u4fee\u590d"]},
        ],
    },
    "T04": {
        "root": "\u5927\u8bed\u8a00\u6a21\u578b\u5e94\u7528\u57fa\u7840",
        "branches": [
            {"text": "\u5927\u8bed\u8a00\u6a21\u578b", "children": ["\u8bad\u7ec3\u4e0e\u5185\u5bb9\u9884\u6d4b", "\u95ee\u7b54\u3001\u603b\u7ed3\u3001\u7ffb\u8bd1\u548c\u751f\u6210", "Token\u4e0e\u4e0a\u4e0b\u6587\u7a97\u53e3"]},
            {"text": "Prompt", "children": ["\u89d2\u8272\u3001\u4efb\u52a1\u548c\u80cc\u666f", "\u8f93\u5165\u3001\u89c4\u5219\u548c\u683c\u5f0f", "\u7ed3\u6784\u5316\u7ea6\u675f\u4e0e\u6821\u9a8c"]},
            {"text": "RAG", "children": ["\u6587\u6863\u5207\u5206\u4e0eEmbedding", "\u5411\u91cf\u5b58\u50a8\u4e0e\u68c0\u7d22", "\u4e0a\u4e0b\u6587\u7ec4\u88c5\u4e0e\u751f\u6210"]},
            {"text": "Agent", "children": ["\u89c4\u5212\u3001\u5de5\u5177\u3001\u72b6\u6001\u548c\u5faa\u73af", "LLM\u3001Prompt\u4e0eTools", "Memory\u3001State\u4e0eGuardrails"]},
            {"text": "\u804c\u8d23\u5206\u914d", "children": ["LLM\uff1a\u7406\u89e3\u3001\u5206\u7c7b\u3001\u89c4\u5212\u3001\u751f\u6210", "\u7a0b\u5e8f\uff1a\u8ba1\u7b97\u3001\u6821\u9a8c\u3001\u6743\u9650\u3001\u5b58\u50a8"]},
            {"text": "\u5b89\u5168\u673a\u5236", "children": ["\u9632\u6ce8\u5165\u4e0e\u4fe1\u606f\u6cc4\u9732", "\u5de5\u5177\u767d\u540d\u5355\u4e0e\u53c2\u6570\u6821\u9a8c", "\u6743\u9650\u3001\u9694\u79bb\u3001\u65e5\u5fd7\u548c\u4eba\u5de5\u786e\u8ba4"]},
        ],
    },
    "T05": {
        "root": "\u4e09\u4e2a\u6708AI\u4ea7\u54c1\u5b9e\u4e60\u6c42\u804c\u8ba1\u5212",
        "branches": [
            {"text": "\u5f53\u524d\u57fa\u7840\u4e0e\u4e0d\u8db3", "children": ["\u524d\u7aef\u3001\u7f16\u7a0b\u548cAI\u8bfe\u7a0b\u57fa\u7840", "\u6811\u8393\u6d3e\u9879\u76ee", "\u7f3a\u4ea7\u54c1\u7ecf\u5386\u3001\u539f\u578b\u3001\u7814\u7a76\u548c\u6570\u636e\u80fd\u529b"]},
            {"text": "\u7b2c\u4e00\u4e2a\u6708\uff1a\u4ea7\u54c1\u57fa\u7840", "children": ["\u4ea7\u54c1\u6d41\u7a0b\u4e0e\u4f18\u5148\u7ea7", "\u7ade\u54c1\u4e0e\u7528\u6237\u7814\u7a76", "\u539f\u578b\u8bbe\u8ba1", "PRD\u5199\u4f5c"]},
            {"text": "\u7b2c\u4e8c\u4e2a\u6708\uff1a\u9879\u76ee\u5b9e\u8df5", "children": ["AI\u6c42\u804c\u5206\u6790Agent", "\u5e02\u573a\u9700\u6c42\u578bAI\u9879\u76ee", "\u5206\u6790\u3001\u539f\u578b\u3001PRD\u3001\u6d4b\u8bd5\u4e0e\u6f14\u793a"]},
            {"text": "\u7b2c\u4e09\u4e2a\u6708\uff1a\u6295\u9012\u9762\u8bd5", "children": ["\u7b5b\u9009\u5c97\u4f4d\u4e0e\u4fee\u6539\u7b80\u5386", "\u8bb0\u5f55\u6295\u9012\u72b6\u6001", "\u51c6\u5907\u9762\u8bd5", "\u9762\u8bd5\u590d\u76d8"]},
            {"text": "\u65f6\u95f4\u548c\u590d\u76d8", "children": ["\u6bcf\u59294\u81f35\u5c0f\u65f6", "\u7406\u8bba\u3001\u9879\u76ee\u3001\u6c42\u804c", "\u6bcf\u5468\u68c0\u67e5\u4e0e\u8c03\u6574"]},
            {"text": "\u6700\u7ec8\u6210\u679c", "children": ["\u4e24\u4efd\u9879\u76ee\u4f5c\u54c1", "\u4e24\u5957\u539f\u578b\u548cPRD", "\u4f18\u5316\u7b80\u5386\u4e0e\u4f5c\u54c1\u96c6", "\u5b8c\u6574\u6295\u9012\u8bb0\u5f55"]},
        ],
    },
    "T06": {
        "root": "\u7528\u6237\u6ce8\u518c\u4e0e\u767b\u5f55",
        "branches": [
            {"text": "\u6ce8\u518c\u65b9\u5f0f", "children": ["\u624b\u673a\u53f7\u4e0e\u9a8c\u8bc1\u7801", "\u90ae\u7bb1\u4e0e\u9a8c\u8bc1\u94fe\u63a5"]},
            {"text": "\u6ce8\u518c\u89c4\u5219", "children": ["\u9a8c\u8bc1\u7801\u6709\u6548\u671f\u548c\u53d1\u9001\u9650\u5236", "\u8bbe\u7f6e\u5bc6\u7801", "\u540c\u610f\u534f\u8bae\u4e0e\u9690\u79c1\u653f\u7b56"]},
            {"text": "\u767b\u5f55\u65b9\u5f0f", "children": ["\u8d26\u53f7\u5bc6\u7801", "\u9a8c\u8bc1\u7801\u767b\u5f55"]},
            {"text": "\u5f02\u5e38\u5904\u7406", "children": ["\u5df2\u6ce8\u518c\u8d26\u53f7\u63d0\u793a", "\u9519\u8bef\u5bc6\u7801\u9501\u5b9a", "\u5fd8\u8bb0\u5bc6\u7801\u4e0e\u91cd\u7f6e"]},
            {"text": "\u8d26\u53f7\u5b89\u5168", "children": ["\u767b\u5f55\u8bb0\u5f55\u4e0e\u65b0\u8bbe\u5907\u901a\u77e5", "\u8bbe\u5907\u7ba1\u7406\u4e0e\u4fee\u6539\u5bc6\u7801", "\u8eab\u4efd\u9a8c\u8bc1\u540e\u6ce8\u9500"]},
        ],
    },
    "T07": {
        "root": "\u4eba\u5de5\u667a\u80fd\u4f53\u9a8c\u65e5\u6267\u884c\u6d41\u7a0b",
        "branches": [
            {"text": "\u524d\u671f\u7acb\u9879", "children": ["\u76ee\u6807\u3001\u4eba\u6570\u3001\u573a\u5730\u548c\u9884\u7b97", "\u63d0\u4ea4\u5b66\u6821\u7533\u8bf7"]},
            {"text": "\u7b79\u5907\u6267\u884c", "children": ["\u573a\u5730\u8bbe\u5907\u4e0e\u5609\u5bbe", "\u5ba3\u4f20\u548c\u62a5\u540d", "\u6536\u96c6\u53c2\u4e0e\u8005\u4fe1\u606f"]},
            {"text": "\u6d3b\u52a8\u524d\u68c0\u67e5", "children": ["\u5609\u5bbe\u4e0e\u8bbe\u5907\u786e\u8ba4", "\u7b7e\u5230\u548c\u6307\u5f15\u6750\u6599", "\u5e94\u6025\u8054\u7cfb\u4eba"]},
            {"text": "\u6d3b\u52a8\u5f53\u5929", "children": ["\u5e03\u7f6e\u4e0e\u7b7e\u5230", "\u5206\u4eab\u548c\u6f14\u793a", "\u63d0\u95ee\u4e0e\u4f53\u9a8c"]},
            {"text": "\u5f02\u5e38\u9884\u6848", "children": ["\u5609\u5bbe\u8fdf\u5230", "\u7f51\u7edc\u6216\u8bbe\u5907\u6545\u969c", "\u4eba\u6570\u8d85\u51fa\u5bb9\u91cf"]},
            {"text": "\u6d3b\u52a8\u590d\u76d8", "children": ["\u6ee1\u610f\u5ea6\u4e0e\u6570\u636e\u6574\u7406", "\u62a5\u9500\u548c\u603b\u7ed3", "\u51b3\u5b9a\u4e0b\u4e00\u671f"]},
        ],
    },
    "T08": {
        "root": "\u7528\u6237\u53cd\u9988\u95ee\u9898\u4e0e\u5904\u7406\u8ba1\u5212",
        "branches": [
            {"text": "\u52a0\u8f7d\u95ee\u9898", "children": ["\u7528\u6237\u611f\u77e5\u7b49\u5f85\u8fc7\u957f", "\u6a21\u578b\u5e73\u5747\u8c03\u7528\u5341\u4e8c\u79d2", "\u8bf7\u6c42\u5b8c\u6210\u540e\u72b6\u6001\u672a\u7ed3\u675f"]},
            {"text": "\u5386\u53f2\u8bb0\u5f55\u95ee\u9898", "children": ["\u6570\u636e\u5e93\u5b58\u5728\u8bb0\u5f55", "\u8be6\u60c5\u63a5\u53e3\u7528\u6237ID\u9519\u8bef"]},
            {"text": "\u5bfc\u56fe\u95ee\u9898", "children": ["\u8282\u70b9\u5206\u6563\u548c\u6587\u5b57\u8fc7\u5c0f", "\u8282\u70b9\u5b58\u5728\u4f46\u6ca1\u6709\u8fde\u7ebf", "\u4f18\u5148\u4fee\u590d\u8fde\u7ebf\u4e0e\u7f29\u653e"]},
            {"text": "\u4f18\u5148\u7ea7", "children": ["\u7b2c\u4e00\uff1a\u72b6\u6001\u3001\u5386\u53f2\u3001\u8fde\u7ebf", "\u7b2c\u4e8c\uff1a\u5e03\u5c40\u3001\u5b57\u53f7\u3001\u63d0\u793a", "\u7b2c\u4e09\uff1a\u6a21\u677f\u548c\u4e3b\u9898\u989c\u8272"]},
            {"text": "\u9a8c\u6536\u8981\u6c42", "children": ["\u8bb0\u5f55\u590d\u73b0\u6761\u4ef6\u4e0e\u6839\u56e0", "\u8bb0\u5f55\u6587\u4ef6\u4e0e\u9a8c\u8bc1\u65b9\u5f0f", "\u771f\u5b9e\u8d26\u53f7\u6d4f\u89c8\u5668\u9a8c\u6536"]},
        ],
    },
    "T09": {
        "root": "RAG\u4f01\u4e1a\u77e5\u8bc6\u5e93\u7cfb\u7edf",
        "branches": [
            {"text": "\u6587\u6863\u63a5\u5165", "children": ["Word\u3001PDF\u3001\u7f51\u9875\u548c\u6587\u672c", "\u683c\u5f0f\u89e3\u6790\u4e0e\u6b63\u6587\u63d0\u53d6", "\u53bb\u91cd\u4e0e\u654f\u611f\u4fe1\u606f\u5904\u7406"]},
            {"text": "\u6587\u6863\u5207\u5206", "children": ["\u6807\u9898\u3001\u6bb5\u843d\u548c\u8bed\u4e49\u8fb9\u754c", "\u63a7\u5236\u6587\u672c\u5757\u957f\u5ea6"]},
            {"text": "\u5411\u91cf\u4e0e\u5143\u6570\u636e", "children": ["\u751f\u6210Embedding\u5e76\u5b58\u50a8", "\u4fdd\u5b58\u6765\u6e90\u3001\u65f6\u95f4\u548c\u6743\u9650"]},
            {"text": "\u68c0\u7d22\u4e0e\u6392\u5e8f", "children": ["\u5411\u91cf\u4e0e\u5173\u952e\u8bcd\u6df7\u5408\u68c0\u7d22", "\u76f8\u5173\u6027\u3001\u6743\u9650\u548c\u65f6\u95f4\u91cd\u6392"]},
            {"text": "\u56de\u7b54\u751f\u6210", "children": ["\u7ec4\u88c5\u8d44\u6599\u4e0e\u95ee\u9898", "\u5f15\u7528\u8d44\u6599\u6765\u6e90", "\u8d44\u6599\u4e0d\u8db3\u65f6\u8bf4\u660e"]},
            {"text": "\u8bc4\u4f30\u4e0e\u5b89\u5168", "children": ["\u53ec\u56de\u3001\u6392\u5e8f\u548c\u7b54\u6848\u51c6\u786e\u7387", "\u5f15\u7528\u3001\u65f6\u95f4\u4e0e\u6210\u672c", "\u9632\u6b62\u8d8a\u6743\u8bbf\u95ee"]},
        ],
    },
    "T10": {
        "root": "\u901a\u4fe1\u539f\u7406\u8003\u8bd5\u590d\u4e60",
        "branches": [
            {"text": "\u6a21\u62df\u8c03\u5236", "children": ["AM\u3001DSB\u3001SSB", "\u9891\u8c31\u3001\u5e26\u5bbd\u3001\u529f\u7387\u548c\u6548\u7387"]},
            {"text": "\u6570\u5b57\u57fa\u5e26\u4f20\u8f93", "children": ["\u7801\u95f4\u4e32\u6270\u4e0e\u5948\u5947\u65af\u7279\u51c6\u5219", "\u5347\u4f59\u5f26\u6eda\u964d\u4e0e\u5747\u8861\u5668"]},
            {"text": "\u6570\u5b57\u8c03\u5236", "children": ["ASK\u3001FSK\u3001PSK\u3001QPSK", "\u6ce2\u5f62\u3001\u5e26\u5bbd\u3001\u8bef\u7801\u7387\u548c\u6297\u566a\u6027"]},
            {"text": "\u4fe1\u6e90\u7f16\u7801", "children": ["\u62bd\u6837\u3001\u91cf\u5316\u3001PCM", "\u8bef\u5dee\u3001\u4f4d\u6570\u3001\u901f\u7387\u548c\u5e26\u5bbd"]},
            {"text": "\u590d\u4e60\u65b9\u6cd5", "children": ["\u6574\u7406\u516c\u5f0f\u548c\u5178\u578b\u9898", "\u6839\u636e\u9519\u9898\u8865\u5145\u8584\u5f31\u70b9"]},
        ],
    },
    "T11": {
        "root": "\u4e2a\u4eba\u8d44\u6599\u4e0e\u9690\u79c1\u8bbe\u7f6e",
        "branches": [
            {"text": "\u5934\u50cf\u4e0a\u4f20", "children": ["JPG\u6216PNG", "\u4e0d\u8d85\u8fc7\u4e94\u5146", "\u9884\u89c8\u540e\u786e\u8ba4\u4fdd\u5b58", "\u5931\u8d25\u65f6\u663e\u793a\u539f\u56e0"]},
            {"text": "\u8d44\u6599\u7f16\u8f91", "children": ["\u6635\u79f0\u975e\u7a7a\u4e14\u6700\u591a\u4e8c\u5341\u5b57", "\u7b80\u4ecb\u6700\u591a\u4e24\u767e\u5b57", "\u4fee\u6539\u6240\u5728\u57ce\u5e02", "\u5931\u8d25\u65f6\u4fdd\u7559\u8f93\u5165"]},
            {"text": "\u9690\u79c1\u8bbe\u7f6e", "children": ["\u63a7\u5236\u8d44\u6599\u662f\u5426\u516c\u5f00", "\u5173\u95ed\u540e\u9690\u85cf\u7b80\u4ecb\u548c\u57ce\u5e02", "\u672c\u4eba\u4ecd\u53ef\u7f16\u8f91", "\u8bb0\u5f55\u66f4\u65b0\u65f6\u95f4"]},
        ],
    },
    "T12": {
        "root": "\u4f01\u4e1a\u95ee\u7b54AI\u5b9e\u73b0\u65b9\u6848\u6bd4\u8f83",
        "branches": [
            {"text": "\u76f4\u63a5\u8c03\u7528LLM", "children": ["\u5f00\u53d1\u6700\u5feb\u3001\u9002\u5408\u9a8c\u8bc1", "\u4e0d\u61c2\u5185\u90e8\u8d44\u6599\u3001\u5bb9\u6613\u5e7b\u89c9"]},
            {"text": "RAG", "children": ["\u77e5\u8bc6\u66f4\u65b0\u65b9\u4fbf\u3001\u53ef\u4ee5\u5f15\u7528\u6765\u6e90", "\u9700\u8981\u6587\u6863\u3001\u68c0\u7d22\u548c\u8bc4\u4f30\u94fe\u8def"]},
            {"text": "\u6a21\u578b\u5fae\u8c03", "children": ["\u5b66\u4e60\u98ce\u683c\u548c\u4efb\u52a1\u683c\u5f0f", "\u6570\u636e\u6210\u672c\u9ad8\u3001\u4e0d\u9002\u5408\u66f4\u65b0\u4e8b\u5b9e"]},
            {"text": "\u5f53\u524d\u9009\u62e9", "children": ["\u516d\u5468\u4e0a\u7ebf\u4e14\u8d44\u6599\u6bcf\u5468\u66f4\u65b0", "V0\u9009\u62e9RAG", "\u76f4\u63a5\u8c03\u7528\u7528\u4e8e\u65e9\u671f\u539f\u578b", "\u5fae\u8c03\u7559\u5f85\u672a\u6765"]},
            {"text": "\u901a\u7528\u8bc4\u4f30", "children": ["\u51c6\u786e\u7387\u3001\u65f6\u95f4\u548c\u6210\u672c", "\u9690\u79c1\u548c\u7ef4\u62a4\u96be\u5ea6", "\u771f\u5b9e\u95ee\u9898\u6d4b\u8bd5\u96c6"]},
        ],
    },
    "T13": {
        "root": "\u5ba2\u670d\u5de5\u5355\u4e8b\u6545\u590d\u76d8",
        "branches": [
            {"text": "\u4e8b\u6545\u73b0\u8c61", "children": ["\u90e8\u5206\u7528\u6237\u65e0\u6cd5\u63d0\u4ea4", "\u9519\u8bef\u7387\u5347\u81f335%", "\u8d44\u6e90\u4f7f\u7528\u6b63\u5e38"]},
            {"text": "\u6839\u56e0", "children": ["\u9644\u4ef6\u5b57\u6bb5\u683c\u5f0f\u4e0d\u4e00\u81f4", "\u524d\u7aef\u6570\u7ec4\u3001\u540e\u7aef\u5b57\u7b26\u4e32", "\u7f3a\u5c11\u591a\u9644\u4ef6\u6d4b\u8bd5"]},
            {"text": "\u5e94\u6025\u5904\u7406", "children": ["\u56de\u6eda\u6062\u590d\u670d\u52a1", "\u517c\u5bb9\u65b0\u65e7\u683c\u5f0f", "\u7528\u6237\u8bf4\u660e\u4e0e\u4eba\u5de5\u767b\u8bb0"]},
            {"text": "\u5f71\u54cd", "children": ["\u6301\u7eed\u56db\u5341\u4e8c\u5206\u949f", "\u7ea6\u4e00\u5343\u4e8c\u767e\u540d\u7528\u6237", "\u4e09\u767e\u591a\u4eba\u91cd\u590d\u63d0\u4ea4"]},
            {"text": "\u6539\u8fdb\u63aa\u65bd", "children": ["Schema\u7248\u672c\u7ba1\u7406", "CI\u5951\u7ea6\u6d4b\u8bd5", "\u7070\u5ea6\u3001\u544a\u8b66\u548c\u56de\u6eda\u6f14\u7ec3", "\u660e\u786e\u8d1f\u8d23\u4eba\u548c\u65f6\u95f4"]},
        ],
    },
    "T14": {
        "root": "\u4ea7\u54c1\u4e0a\u7ebf\u524d\u68c0\u67e5",
        "branches": [
            {"text": "\u524d\u7aef\u68c0\u67e5", "children": ["\u529f\u80fd\u6d4b\u8bd5\uff1a\u6309\u94ae\u3001\u8868\u5355\u3001\u8df3\u8f6c", "\u6027\u80fd\u6d4b\u8bd5\uff1a\u52a0\u8f7d\u548c\u4ea4\u4e92", "\u5b89\u5168\u6d4b\u8bd5\uff1a\u5bc6\u94a5\u548c\u654f\u611f\u4fe1\u606f"]},
            {"text": "\u540e\u7aef\u68c0\u67e5", "children": ["\u529f\u80fd\u6d4b\u8bd5\uff1a\u63a5\u53e3\u4e1a\u52a1\u903b\u8f91", "\u6027\u80fd\u6d4b\u8bd5\uff1a\u5e76\u53d1\u3001\u67e5\u8be2\u3001\u54cd\u5e94", "\u5b89\u5168\u6d4b\u8bd5\uff1a\u9274\u6743\u3001\u8d8a\u6743\u3001\u6ce8\u5165"]},
            {"text": "AI\u6a21\u5757\u68c0\u67e5", "children": ["\u529f\u80fd\u6d4b\u8bd5\uff1a\u4efb\u52a1\u548c\u7ed3\u6784\u5316\u8f93\u51fa", "\u6027\u80fd\u6d4b\u8bd5\uff1a\u54cd\u5e94\u65f6\u95f4\u548c\u6210\u672c", "\u5b89\u5168\u6d4b\u8bd5\uff1aPrompt\u6ce8\u5165\u548c\u5de5\u5177\u8c03\u7528"]},
        ],
    },
    "T15": {
        "root": "\u5b66\u4e60\u8d44\u6599\u601d\u7ef4\u5bfc\u56fe\u4ea7\u54c1V0",
        "branches": [
            {"text": "\u7528\u6237\u4e0e\u95ee\u9898", "children": ["\u5927\u5b66\u751f\u5904\u7406\u8bfe\u7a0b\u548c\u4e13\u4e1a\u8d44\u6599", "\u5185\u5bb9\u5206\u6563", "\u96be\u4ee5\u53d1\u73b0\u77e5\u8bc6\u5173\u7cfb"]},
            {"text": "V0\u6838\u5fc3\u529f\u80fd", "children": ["\u7c98\u8d34\u957f\u6587\u672c\u5e76\u751f\u6210\u5bfc\u56fe", "\u67e5\u770b\u539f\u6587\u4e0e\u91cd\u65b0\u751f\u6210", "\u4fdd\u5b58\u5386\u53f2\u8bb0\u5f55"]},
            {"text": "\u8f93\u5165\u4e0e\u751f\u6210\u72b6\u6001", "children": ["\u4e09\u4e07\u5b57\u3001\u5b57\u7b26\u6570\u548c\u8d85\u9650\u63d0\u793a", "\u6807\u9898\u3001\u5c42\u7ea7\u548c\u539f\u6587\u9650\u5236", "\u9632\u91cd\u590d\u63d0\u4ea4\u4e0e\u5206\u6b65\u8fdb\u5ea6"]},
            {"text": "\u540e\u7aef\u5904\u7406", "children": ["\u6e05\u6d17\u4e0e\u8bed\u4e49\u5207\u5206", "\u4fdd\u6301\u987a\u5e8f\u3001\u6765\u6e90\u548c\u5b8c\u6574\u6027", "LLM\u8d1f\u8d23\u8bed\u4e49\u7ed3\u6784", "\u7a0b\u5e8f\u8d1f\u8d23\u6821\u9a8c\u3001ID\u3001\u4fdd\u5b58\u548c\u8f6c\u6362"]},
            {"text": "\u6570\u636e\u4e0e\u6821\u9a8c", "children": ["\u8282\u70b9\u7ed3\u6784\u5b57\u6bb5", "ID\u3001\u7236\u8282\u70b9\u3001\u5faa\u73af\u548c\u5c42\u7ea7\u68c0\u67e5", "\u9519\u8bef\u8fd4\u56de\u6a21\u578b\u4e14\u6700\u591a\u4fee\u590d\u4e24\u6b21", "\u5931\u8d25\u65f6\u663e\u793a\u771f\u5b9e\u9519\u8bef"]},
            {"text": "\u5bfc\u56fe\u4ea4\u4e92", "children": ["\u4e2d\u5fc3\u4e3b\u9898\u548c\u5de6\u53f3\u5e03\u5c40", "\u7236\u5b50\u8282\u70b9\u53ef\u89c1\u8fde\u7ebf", "\u6362\u884c\u3001\u4e0d\u91cd\u53e0\u3001\u7f29\u653e\u548c\u6298\u53e0", "\u590d\u5236\u3001PNG\u548c\u5386\u53f2\u8bb0\u5f55"]},
            {"text": "\u4fdd\u5b58\u4e0e\u6743\u9650", "children": ["\u4fdd\u5b58\u6587\u672c\u3001\u53c2\u6570\u3001\u7ed3\u6784\u548c\u6821\u9a8c", "\u5237\u65b0\u540e\u4fdd\u6301\u4e00\u81f4", "\u7528\u6237\u6570\u636e\u9694\u79bb"]},
            {"text": "\u6d4b\u8bd5\u9a8c\u6536", "children": ["\u8f93\u5165\u3001\u7ed3\u6784\u3001\u6a21\u578b\u548c\u6570\u636e\u5e93\u5f02\u5e38", "\u5355\u5143\u4e0e\u63a5\u53e3\u6d4b\u8bd5", "\u771f\u5b9e\u6d4f\u89c8\u5668\u7aef\u5230\u7aef\u6d4b\u8bd5", "\u4fdd\u5b58\u53ef\u590d\u6838\u8bc1\u636e"]},
        ],
    },
}


def semantic_match(actual_text, expected_text):
    """Check if actual_text semantically matches expected_text.
    Uses multiple strategies optimized for Chinese text comparison.
    """
    generic_placeholders = ["\u77e5\u8bc6\u5bfc\u56fe", "\u91cd\u70b9\u5185\u5bb9", "\u6838\u5fc3\u6982\u5ff5", "\u590d\u4e60\u7ebf\u7d22", "\u5176\u4ed6\u5185\u5bb9", "\u5176\u4ed6", "\u603b\u7ed3"]
    if actual_text.strip() in generic_placeholders:
        return False

    a = actual_text.strip()
    b = expected_text.strip()

    if a == b:
        return True

    punct = r'[\uff1a\uff1b\uff0c\u3001\uff08\uff09:;,.()\s\-\u2014\u3000]'
    a_clean = re.sub(punct, '', a)
    b_clean = re.sub(punct, '', b)

    if a_clean == b_clean:
        return True

    # Strategy 1: Direct substring containment
    if len(a_clean) >= 2 and len(b_clean) >= 2:
        if a_clean in b_clean or b_clean in a_clean:
            return True

    # Strategy 2: Character bigram Dice coefficient
    def get_bigrams(s):
        return set(s[i:i+2] for i in range(len(s)-1)) if len(s) >= 2 else {s}

    a_bigrams = get_bigrams(a_clean)
    b_bigrams = get_bigrams(b_clean)

    if a_bigrams and b_bigrams:
        intersection = a_bigrams & b_bigrams
        dice = 2 * len(intersection) / (len(a_bigrams) + len(b_bigrams))
        if dice >= 0.45:
            return True

    # Strategy 3: Split on separators and check sub-part matching
    sep_pattern = r'[\u3001\uff0c\u548c\u4e0e\u53ca/]'
    a_parts = [p.strip() for p in re.split(sep_pattern, a_clean) if len(p.strip()) >= 1]
    b_parts = [p.strip() for p in re.split(sep_pattern, b_clean) if len(p.strip()) >= 1]

    if len(b_parts) >= 2:
        matched_parts = 0
        for bp in b_parts:
            for ap in a_parts:
                if bp in ap or ap in bp:
                    matched_parts += 1
                    break
                if len(bp) >= 2 and len(ap) >= 2:
                    bp_bi = get_bigrams(bp)
                    ap_bi = get_bigrams(ap)
                    if bp_bi and ap_bi:
                        part_dice = 2 * len(bp_bi & ap_bi) / (len(bp_bi) + len(ap_bi))
                        if part_dice >= 0.5:
                            matched_parts += 1
                            break
        part_recall = matched_parts / len(b_parts)
        if part_recall >= 0.6:
            return True

    # Strategy 4: Character-level Jaccard on meaningful chars
    common_chars = set("\u7684\u4e86\u662f\u5728\u6709\u548c\u4e0e\u53ca\u7b49\u4e0d\u5230\u4e3a\u88ab\u6240\u4ece")
    a_chars = set(a_clean) - common_chars
    b_chars = set(b_clean) - common_chars
    if a_chars and b_chars:
        jaccard = len(a_chars & b_chars) / len(a_chars | b_chars)
        if jaccard >= 0.45:
            return True

    return False


def evaluate_case(case_id, standard, frozen_path):
    """Evaluate S4 for a single case. Returns (pass: bool, details: dict)."""
    with open(frozen_path, 'r', encoding='utf-8') as f:
        frozen = json.load(f)

    nodes = frozen["nodes"]
    if not nodes:
        return False, {"error": "no nodes in frozen data"}

    node_by_id = {n["id"]: n for n in nodes}
    root_nodes = [n for n in nodes if n.get("parent_id") is None or n.get("level") == 0]
    l1_nodes = [n for n in nodes if n.get("level") == 1]

    details = {
        "case_id": case_id,
        "total_nodes": len(nodes),
        "l1_count": len(l1_nodes),
    }

    # Criterion 1: Central topic correct
    root_text = root_nodes[0]["text"] if root_nodes else ""
    root_correct = semantic_match(root_text, standard["root"])
    details["root_text_actual"] = root_text
    details["root_text_expected"] = standard["root"]
    details["root_correct"] = root_correct

    # Criterion 2: L1 branch recall
    expected_l1 = [b["text"] for b in standard["branches"]]
    actual_l1_texts = [n["text"] for n in l1_nodes]

    l1_matched = []
    l1_missed = []
    matched_indices = set()
    for exp_branch in expected_l1:
        found = False
        for i, act in enumerate(actual_l1_texts):
            if i not in matched_indices and semantic_match(act, exp_branch):
                l1_matched.append({"expected": exp_branch, "actual": act})
                matched_indices.add(i)
                found = True
                break
        if not found:
            l1_missed.append(exp_branch)

    l1_recall = len(l1_matched) / len(expected_l1) if expected_l1 else 1.0
    details["l1_expected"] = expected_l1
    details["l1_actual"] = actual_l1_texts
    details["l1_matched"] = l1_matched
    details["l1_missed"] = l1_missed
    details["l1_recall"] = l1_recall

    # Criterion 3: Knowledge point recall (L2+)
    expected_l2_all = []
    for b in standard["branches"]:
        expected_l2_all.extend(b["children"])

    actual_l2_texts = [n["text"] for n in nodes if n.get("level", 0) >= 2]

    l2_matched = []
    l2_missed = []
    used_actual = set()
    for exp_kp in expected_l2_all:
        found = False
        for i, act in enumerate(actual_l2_texts):
            if i not in used_actual and semantic_match(act, exp_kp):
                l2_matched.append({"expected": exp_kp, "actual": act})
                used_actual.add(i)
                found = True
                break
        if not found:
            l2_missed.append(exp_kp)

    l2_recall = len(l2_matched) / len(expected_l2_all) if expected_l2_all else 1.0
    details["l2_expected_count"] = len(expected_l2_all)
    details["l2_matched_count"] = len(l2_matched)
    details["l2_missed"] = l2_missed
    details["l2_recall"] = l2_recall

    # Criterion 4: Parent-child relationship correctness
    pc_correct = 0
    pc_total = 0
    pc_errors = []

    for std_branch in standard["branches"]:
        actual_l1_node = None
        for n in l1_nodes:
            if semantic_match(n["text"], std_branch["text"]):
                actual_l1_node = n
                break

        if not actual_l1_node:
            pc_total += len(std_branch["children"])
            for child in std_branch["children"]:
                pc_errors.append({"expected_parent": std_branch["text"], "child": child, "error": "parent_not_found"})
            continue

        # Get all descendants of this L1 node
        actual_children_ids = set()
        queue = [actual_l1_node["id"]]
        while queue:
            pid = queue.pop(0)
            for n in nodes:
                if n.get("parent_id") == pid:
                    actual_children_ids.add(n["id"])
                    queue.append(n["id"])

        actual_children_texts = [node_by_id[cid]["text"] for cid in actual_children_ids if cid in node_by_id]

        for exp_child in std_branch["children"]:
            pc_total += 1
            child_found = False
            for act_child_text in actual_children_texts:
                if semantic_match(act_child_text, exp_child):
                    child_found = True
                    break
            if child_found:
                pc_correct += 1
            else:
                pc_errors.append({"expected_parent": std_branch["text"], "child": exp_child, "error": "child_not_under_parent"})

    pc_accuracy = pc_correct / pc_total if pc_total > 0 else 1.0
    details["pc_total"] = pc_total
    details["pc_correct"] = pc_correct
    details["pc_accuracy"] = pc_accuracy
    details["pc_errors"] = pc_errors[:10]

    # Criterion 5: No fabrication
    fabricated_l1 = []
    for act_text in actual_l1_texts:
        is_matched = False
        for exp_branch in expected_l1:
            if semantic_match(act_text, exp_branch):
                is_matched = True
                break
        if not is_matched:
            fabricated_l1.append(act_text)

    details["fabricated_l1"] = fabricated_l1
    no_fabrication = len(fabricated_l1) == 0

    # Binary decision
    s4_pass = (
        root_correct
        and l1_recall >= 0.9
        and l2_recall >= 0.9
        and pc_accuracy >= 0.9
        and no_fabrication
    )

    details["s4_binary"] = 1 if s4_pass else 0
    details["fail_reasons"] = []
    if not root_correct:
        details["fail_reasons"].append(f"root mismatch: got '{root_text}' expected '{standard['root']}'")
    if l1_recall < 0.9:
        details["fail_reasons"].append(f"L1 recall {l1_recall:.2f} < 0.9, missed: {l1_missed}")
    if l2_recall < 0.9:
        details["fail_reasons"].append(f"L2 recall {l2_recall:.2f} < 0.9, missed: {l2_missed[:5]}")
    if pc_accuracy < 0.9:
        details["fail_reasons"].append(f"parent-child accuracy {pc_accuracy:.2f} < 0.9")
    if not no_fabrication:
        details["fail_reasons"].append(f"fabricated L1 branches: {fabricated_l1}")

    return s4_pass, details


def main():
    results = {}
    print("=" * 70)
    print("S4 BINARY EVALUATION: LLM Output vs Standard Answers")
    print("=" * 70)

    for i in range(1, 16):
        cid = f"T{i:02d}"
        frozen_path = os.path.join(OUTPUT_DIR, cid, "frozen-data.json")
        if not os.path.exists(frozen_path):
            print(f"  [{cid}] SKIP - frozen-data.json not found")
            results[cid] = {"s4_binary": 0, "error": "frozen data missing"}
            continue

        s4_pass, details = evaluate_case(cid, STANDARD_ANSWERS[cid], frozen_path)
        results[cid] = details

        status = "PASS (1)" if s4_pass else "FAIL (0)"
        print(f"\n  [{cid}] {status}")
        print(f"    Root: {'OK' if details['root_correct'] else 'MISMATCH'} (actual='{details['root_text_actual']}')")
        print(f"    L1 recall: {details['l1_recall']:.2f} ({len(details['l1_matched'])}/{len(STANDARD_ANSWERS[cid]['branches'])})")
        print(f"    L2 recall: {details['l2_recall']:.2f} ({details['l2_matched_count']}/{details['l2_expected_count']})")
        print(f"    Parent-child: {details['pc_accuracy']:.2f} ({details['pc_correct']}/{details['pc_total']})")
        print(f"    Fabricated L1: {details['fabricated_l1']}")
        if details.get("fail_reasons"):
            for r in details["fail_reasons"]:
                print(f"    FAIL: {r}")

    # Save results
    output_path = os.path.join(OUTPUT_DIR, "s4-semantic-comparison.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Summary
    passed = sum(1 for r in results.values() if r.get("s4_binary") == 1)
    print(f"\n{'=' * 70}")
    print(f"S4 SUMMARY: {passed}/15 PASS")
    print(f"{'=' * 70}")

    for i in range(1, 16):
        cid = f"T{i:02d}"
        r = results[cid]
        mark = "1" if r.get("s4_binary") == 1 else "0"
        reasons = "; ".join(r.get("fail_reasons", [])) if r.get("fail_reasons") else "all criteria met"
        print(f"  {cid}: {mark}  ({reasons})")


if __name__ == "__main__":
    main()
