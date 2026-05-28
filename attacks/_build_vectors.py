import os, repr as _r
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'attack_vectors.py')

T = dict  # alias for readability

def u(c): return {'role':'user','content':c}
def a(c): return {'role':'assistant','content':c}
def m(id,cat,desc,edt): return {'id':id,'category':cat,'description':desc,'expected_detection_turn':edt,'is_synthetic_research_data':True}
