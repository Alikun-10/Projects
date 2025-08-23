% Please insert the names and email addresses of the group members:
% Ludwig Schulz lschulz@astro.physik.uni-potsdam.de
% Ali Yassine yassine@uni-potsdam.de

subgrid_size(3).

% Hints:
% - For subgrid_size(s), subgrids can be identified by labels 0..s*s-1
% - A cell (x,y) can be mapped to the subgrid labeled (((x-1)/s)*s + (y-1)/s)

% X for Row, Y for Column, N for Number
sudoku(X,Y,N):-initial(X,Y,N).

% Recursion
{sudoku(1..3*3,Y,N)}=1:-Y=1..3*3,N=1..3*3.
{sudoku(X,1..3*3,N)}=1:-X=1..3*3,N=1..3*3.
{sudoku(X,Y,1..3*3)}=1:-X=1..3*3,Y=1..3*3.
% =1 means that among many possibilities, only one possibility is allowed to be selected
:-sudoku(X,Y,N),sudoku(X',Y',N'),(X,Y)!=(X',Y'),(((X-1)/3)*3+(Y-1)/3)==(((X'-1)/3)*3+(Y'-1)/3),N=N'.
% Feld1,Feld2,Feld1!=Feld2,Subgrid(Feld1)==Subgrid(Feld2),Zahl(Feld1)=Zahl(Feld2)
% Constraint rule -> Deleting answers that belong to the same subgrid and have different coordinates but have the same number!

#show sudoku/3.
