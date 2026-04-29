const express = require("express");
const fs = require("fs");
const path = require("path");

const app = express();

app.get("/download", (req, res) => {
  const file = path.join("/srv/uploads", req.query.file);
  res.send(fs.readFileSync(file));
});
