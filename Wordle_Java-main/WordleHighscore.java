import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;
import java.util.Scanner;

public class WordleHighscore {

    public static void main(String[] args) {
        // Create a scanner for user input
        Scanner scanner = new Scanner(System.in);
        
        // Ask the user to input their username
        System.out.print("Please enter the username: ");
        String user = scanner.nextLine();
        
        // Get the highscore for the entered username
        String highscore = getUserHighscore(user);
        
        // Output the result
        System.out.println("Highscore of " + user + ": " + highscore);
        
        // Close the scanner
        scanner.close();
    }

    public static String getUserHighscore(String username) {
        String fileName = "scores.txt";  // The path to your file
        String line;
        String[] parts;
        
        try (BufferedReader br = new BufferedReader(new FileReader(fileName))) {
            // Read the file line by line
            while ((line = br.readLine()) != null) {
                // Skip empty lines or lines that do not contain a comma
                if (line.trim().isEmpty() || !line.contains(",")) {
                    continue;  // Skip empty lines or lines without a comma
                }
                
                parts = line.split(",");  // Split by comma
                
                // Make sure there are exactly two parts (username and score)
                if (parts.length == 2) {
                    String user = parts[0].trim();  // Username (remove leading/trailing spaces)
                    String score = parts[1].trim();  // Score (remove leading/trailing spaces)
                    
                    // Check if the username matches
                    if (user.equalsIgnoreCase(username)) {
                        return score;  // Return the highscore for the user
                    }
                }
            }
        } catch (IOException e) {
            e.printStackTrace();
        }
        
        // If the username is not found, return "0" (or another default value)
        return "0";
    }
}
