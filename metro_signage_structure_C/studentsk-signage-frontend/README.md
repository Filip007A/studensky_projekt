# Studentsk Signage Project

This project is a signage prototype that displays real-time departure information using WebSocket connections. It includes a fallback mechanism to show local data when offline.

## Project Structure

```
studentsk-signage-frontend
├── src
│   ├── index.html        # Main HTML document for the application
│   ├── js
│   │   └── app.js       # JavaScript code for WebSocket handling and data display
│   └── css
│       └── styles.css    # CSS styles for the application
├── package.json          # npm configuration file
├── .gitignore            # Files and directories to be ignored by Git
└── README.md             # Documentation for the project
```

## Setup Instructions

1. Clone the repository:
   ```
   git clone <repository-url>
   ```

2. Navigate to the project directory:
   ```
   cd studentsk-signage-frontend
   ```

3. Install the dependencies:
   ```
   npm install
   ```

4. Open `src/index.html` in a web browser to view the application.

## Usage Guidelines

- The application connects to a WebSocket server to receive real-time updates on departures.
- If the connection is lost, it will display fallback data from a local API.
- The status of the connection is displayed at the top of the page.

## Contributing

Feel free to submit issues or pull requests for improvements or bug fixes.