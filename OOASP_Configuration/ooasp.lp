% Please insert the names and email addresses of the group members:
% Janik Achinger
% Ali Yassine yassine@uni-potsdam.de

#const max_instance_per_leaf_class = 10.
#const int_domain_max = 20.

possible_instance_id(1..max_instance_per_leaf_class).

% generate attribute values
int_value(1..int_domain_max).
bool_value("TRUE").
bool_value("FALSE").

% input handling
ooasp_instantiation(M,I) :- partial(ooasp_instantiation(M,I)).
ooasp_isa(I,C,O) :- partial(ooasp_isa(I,C,O)).
ooasp_associated(I,A,O1,O2) :- partial(ooasp_associated(I,A,O1,O2)).
ooasp_attribute_value(I,AT,O,V) :- partial(ooasp_attribute_value(I,AT,O,V)).

% generate instantiation 
ooasp_instantiation(M, I) :- ooasp_isa(I, C, O), ooasp_class(M, C).

% instantiate objects using possible instance ids
{ ooasp_isa(I, C, (C,O)) } :-
	ooasp_instantiation(M, I), ooasp_class(M, C), not ooasp_subclass(M, _, C), possible_instance_id(O).

%
% Your encoding goes here...
%

% instantiate objects using possible instance ids
{ ooasp_isa(Inst, Cls, (Cls,ObjID)) } :- 
    ooasp_instantiation(Mod, Inst), 
    ooasp_class(Mod, Cls), 
    not ooasp_subclass(Mod, _, Cls), 
    possible_instance_id(ObjID).

% inherit attributes from parent to subclasses
ooasp_attribute(Mod, SubCls, Attr, Type) :- 
    ooasp_attribute(Mod, SuperCls, Attr, Type), 
    ooasp_subclass(Mod, SubCls, SuperCls).

% inherit associations to subclasses
ooasp_assoc(Mod, Rel, ClsA, MinA, MaxA, SubClsB, MinB, MaxB) :- 
    ooasp_assoc(Mod, Rel, ClsA, MinA, MaxA, ClsB, MinB, MaxB), 
    ooasp_subclass(Mod, SubClsB, ClsB).

ooasp_assoc(Mod, Rel, SubClsA, MinA, MaxA, ClsB, MinB, MaxB) :- 
    ooasp_assoc(Mod, Rel, ClsA, MinA, MaxA, ClsB, MinB, MaxB), 
    ooasp_subclass(Mod, SubClsA, ClsA).

% final associations only between leaf classes
final(Mod, Rel, LeafA, LeafB) :- 
    ooasp_assoc(Mod, Rel, LeafA, _, _, LeafB, _, _), 
    not ooasp_subclass(Mod, _, LeafA), 
    not ooasp_subclass(Mod, _, LeafB).

% associate objects
{ ooasp_associated(Inst, Rel, ObjA, ObjB) } :- 
    ooasp_instantiation(Mod, Inst), 
    ooasp_assoc(Mod, Rel, ClsX, _, _, ClsY, _, _), 
    ooasp_isa(Inst, ClsX, ObjA), 
    ooasp_isa(Inst, ClsY, ObjB).

% assign values based on attribute type
{ ooasp_attribute_value(Inst, Attr, Obj, Val) : int_value(Val) } :- 
    ooasp_instantiation(Mod, Inst), 
    ooasp_isa(Inst, Cls, Obj), 
    ooasp_attribute(Mod, Cls, Attr, "integer").

{ ooasp_attribute_value(Inst, Attr, Obj, Val) : bool_value(Val) } :- 
    ooasp_instantiation(Mod, Inst), 
    ooasp_isa(Inst, Cls, Obj), 
    ooasp_attribute(Mod, Cls, Attr, "boolean").

{ ooasp_attribute_value(Inst, Attr, Obj, Val) : ooasp_attribute_enum(Mod, Cls, Attr, Val) } :- 
    ooasp_instantiation(Mod, Inst), 
    ooasp_isa(Inst, Cls, Obj), 
    ooasp_attribute(Mod, Cls, Attr, "string").

% ensure one attribute value per object/attribute
:- ooasp_instantiation(Mod, Inst), 
   ooasp_attribute(Mod, Cls, Attr, _), 
   ooasp_isa(Inst, Cls, Obj), 
   not ooasp_attribute_value(Inst, Attr, Obj, _).

:- ooasp_attribute_value(Inst, Attr, Obj, V1), 
   ooasp_attribute_value(Inst, Attr, Obj, V2), 
   V1 != V2.

% numeric value boundaries
:- ooasp_attribute_value(Inst, Attr, Obj, Val), 
   ooasp_attribute_minInclusive(Mod, Cls, Attr, MinVal), 
   ooasp_attribute(Mod, Cls, Attr, "integer"), 
   Val < MinVal.

:- ooasp_attribute_value(Inst, Attr, Obj, Val), 
   ooasp_attribute_maxInclusive(Mod, Cls, Attr, MaxVal), 
   ooasp_attribute(Mod, Cls, Attr, "integer"), 
   Val > MaxVal.

% min/max association constraints (right side)
:- ooasp_instantiation(Mod, Inst), 
   ooasp_assoc(Mod, Rel, SrcCls, _, _, TgtCls, MinTgt, _), 
   ooasp_isa(Inst, SrcCls, Source), MinTgt > 0,
   Cnt = #count { Target : ooasp_isa(Inst, SubTgt, Target), final(Mod, Rel, _, SubTgt), ooasp_associated(Inst, Rel, Source, Target) },
   Cnt < MinTgt.

:- ooasp_instantiation(Mod, Inst), 
   ooasp_assoc(Mod, Rel, SrcCls, _, _, TgtCls, _, MaxTgt), 
   ooasp_isa(Inst, SrcCls, Source), 
   Cnt = #count { Target : ooasp_isa(Inst, SubTgt, Target), final(Mod, Rel, _, SubTgt), ooasp_associated(Inst, Rel, Source, Target) },
   Cnt > MaxTgt.

% min/max association constraints (left side)
:- ooasp_instantiation(Mod, Inst), 
   ooasp_assoc(Mod, Rel, SrcCls, MinSrc, _, TgtCls, _, _), 
   ooasp_isa(Inst, TgtCls, Target), MinSrc > 0,
   Cnt = #count { Source : ooasp_isa(Inst, SubSrc, Source), final(Mod, Rel, SubSrc, _), ooasp_associated(Inst, Rel, Source, Target) },
   Cnt < MinSrc.

:- ooasp_instantiation(Mod, Inst), 
   ooasp_assoc(Mod, Rel, SrcCls, _, MaxSrc, TgtCls, _, _), 
   ooasp_isa(Inst, TgtCls, Target),
   Cnt = #count { Source : ooasp_isa(Inst, SubSrc, Source), final(Mod, Rel, SubSrc, _), ooasp_associated(Inst, Rel, Source, Target) },
   Cnt > MaxSrc.


% symmetry breaking and minimization

% instantiation of objects must be done in ascending order with no
% gaps, unless the objects is given as part of the input partial
% instantiation
:- ooasp_isa(I, C, (C,ID1)), not partial(ooasp_isa(I, C, (C,ID1))),
	 possible_instance_id(ID2), ID2 < ID1, not ooasp_isa(I, C, (C,ID2)).

% for each association, the mapping from the first object to the
% second must be monotonic, unless the association is given as part of
% the input partial instantiation
:- ooasp_associated(I,A,O1,O2), not partial(ooasp_associated(I,A,O1,O2)),
	 ooasp_associated(I,A,O3,O4),  not partial(ooasp_associated(I,A,O3,O4)),
	 O1 < O3, O4 < O2.

% minimize number of instantiated objects
#minimize { 1, I, C, O : ooasp_isa(I, C, O) }.

#show ooasp_instantiation/2.
#show ooasp_isa/3.
#show ooasp_associated/4.
#show ooasp_attribute_value/4.

#defined ooasp_attribute_enum/4.
#defined partial/1.
