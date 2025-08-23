#include "../modules-config-model.lp".

% Partial configuration

partial(ooasp_instantiation("v1","inst")).
partial(ooasp_isa("inst", "Frame", ("Frame", 1))).
partial(ooasp_isa("inst", "ModuleA", ("ModuleA", 2))).
partial(ooasp_isa("inst", "ModuleB", ("ModuleB", 3))).
partial(ooasp_isa("inst","ElementA", ("ElementA", 4))).

partial(ooasp_associated("inst", "Frame_modules", ("Frame", 1), ("ModuleA", 2))).
