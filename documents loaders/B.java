import java.util.Scanner;

class Bob{
public static void main(String args[]){

Scanner scn=new Scanner(System.in);

System.out.print("enter row size:");
int row=scn.nextInt();

System.out.print("enter column size:");
int column=scn.nextInt();

int arr1[][]=new int[row][column];

System.out.println("Enter the elements of 1st Matrix:");

for(int i=0;i<row;i++){
 for(int j=0;j<column;j++){
         arr1[i][j]=scn.nextInt();
 }
}
 
int arr2[][]=new int[row][column];

System.out.println("enter the elements of 2nd matrix:");
for(int a=0;a<row;a++){
 for(int b=0;b<column;b++){
         arr2[a][b]=scn.nextInt();
 }
}

System.out.println("Sum of 1st and 2nd matrix:");
for(int x=0;x<row;x++){
 for(int y=0;y<column;y++){
     int sum[][]=new int[row][column];
      sum[x][y]=arr1[x][y]+arr2[x][y];
 System.out.print(sum[x][y]+" ");
 }
 System.out.println();
}
}
}

