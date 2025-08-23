#include "../bike-config-model.lp".

partial(ooasp_instantiation("v1","c1")).
partial(ooasp_isa("c1","Frame",("Frame",1))).
partial(ooasp_isa("c1","WheelFront",("WheelFront",2))).
partial(ooasp_isa("c1","WheelBack",("WheelBack",3))).
partial(ooasp_associated("c1","Frame_wheel_front",("Frame",1),("WheelFront",2))).
partial(ooasp_associated("c1","Frame_wheel_back",("Frame",1),("WheelBack",3))).
partial(ooasp_attribute_value("c1","child_model",("Frame",1),"TRUE")).
partial(ooasp_attribute_value("c1","gears",("Frame",1),"Hub")).
