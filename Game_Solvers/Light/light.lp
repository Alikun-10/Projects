% INSERT NAMES AND EMAIL ADDRESSES OF YOUR GROUP MEMBERS:
% Ludwig Schulz lschulz@astro.physik.uni-potsdam.de
% Ali Yassine yassine@uni-potsdam.de


rows(1..I):- rows(I).
cols(1..J):- cols(J).
index(0..4).
empty(I,J) :- digit(I,J,Z).
white(I,J) :- not empty(I,J), rows(I), cols(J).

neighbor(I, J, I1, J1) :- |I-I1| + |J-J1| == 1, rows(I), rows(I1), cols(J), cols(J1).
Z{light(I1,J1) : neighbor(I, J, I1, J1), white(I1, J1)}Z :- digit(I,J,Z), index(Z).

lightbulb(X,Y) :- light(X, Y1),  white(X,Y), Y1 < Y, {empty(X,K) :  Y1 < K , K < Y}0.  %right
lightbulb(X,Y) :- light(X, Y1), white(X,Y), Y1 > Y, {empty(X,K) :  Y1 > K, K > Y}0. % left
lightbulb(X,Y) :- light(X1, Y),  white(X,Y), X1 < X, {empty(M,Y) : X1 < M, M < X}0. % up
lightbulb(X,Y) :- light(X1, Y),  white(X,Y), X1 > X, {empty(M,Y) : X1 > M, M > X}0. % down
lightbulb(X,Y) :- light (X,Y).

%For every white cell, generate light such that it is not neighbor of any digit square 
{light(X,Y): digit(X1, Y1, Z), not neighbor(X1, Y1, X, Y)} :- white(X,Y) ,rows(X), cols(Y).

:- white(X,Y), not lightbulb(X,Y).

:- light(X,Y), light(X,Y1), Y != Y1, Y<Y1,{empty(X,Y2): Y < Y2, Y2 < Y1}0.%right
:- light(X,Y), light(X,Y1), Y != Y1, Y>Y1,{empty(X,Y2): Y > Y2, Y2 > Y1}0.%left
:- light(X,Y), light(X1,Y), X!=X1, X<X1,{empty(X2,Y): X < X2, X2 < X1}0.%up
:- light(X,Y), light(X1,Y), X!=X1, X>X1,{empty(X2,Y): X > X2, X2 > X1}0.%down




#show light/2.
